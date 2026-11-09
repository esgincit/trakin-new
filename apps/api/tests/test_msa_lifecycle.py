"""MSA lifecycle between two companies: pending → accepted | rejected → expired, one live MSA per pair,
and renewal requests the other company accepts or declines with a note."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text

from app.db import get_engine


async def _counterparty(user_ids: dict) -> tuple[str, str]:
    """A second workspace that is a company in its own right; its finance2 user is the owner.
    Returns (tenant_id, company_id)."""
    async with get_engine().begin() as conn:
        tenant = (await conn.execute(text(
            "insert into mytrakin.tenants (name, status) values ('Counterparty MSA Workspace', 'active') returning id"))).scalar()
        company = (await conn.execute(text(
            """insert into mytrakin.companies (tenant_id, name, kind, kinds, status)
                values (:t, 'Accepting Partner LLC', 'vendor', array['vendor'], 'active') returning id"""),
            {"t": tenant})).scalar()
        member = (await conn.execute(text(
            """insert into mytrakin.memberships (tenant_id, user_id, role, status)
                values (:t, :u, 'tenant_admin', 'active') returning id"""),
            {"t": tenant, "u": user_ids["finance2"]})).scalar()
        await conn.execute(text("update mytrakin.tenants set company_id = :c, owner_membership_id = :m where id = :t"),
                           {"c": company, "m": member, "t": tenant})
    return str(tenant), str(company)


async def test_a_signature_is_never_refused_by_the_one_live_msa_rule(client, auth, user_ids):
    """Signing must not be blocked by bookkeeping.

    Velocity raised a counter-MSA while DREP's was still out for signature (the rule only
    counts pending/accepted/active as live), so the pair ended up with two unsigned MSAs.
    When the last signer finished, the update to 'accepted' tripped the rule and aborted
    the whole transaction -- a real signature reported as an error.
    """
    today = date.today()
    created: list[str] = []
    async with get_engine().begin() as conn:
        t1 = (await conn.execute(text(
            "insert into mytrakin.tenants (name, status) values ('Signfix Alpha', 'active')"))).scalar()
        c1 = (await conn.execute(text(
            """insert into mytrakin.companies (tenant_id, name, kind, kinds, status)
                values (:t, 'Signfix Alpha Co', 'vendor', array['vendor'], 'active')"""), {"t": t1})).scalar()
        t2 = (await conn.execute(text(
            "insert into mytrakin.tenants (name, status) values ('Signfix Beta', 'active')"))).scalar()
        c2 = (await conn.execute(text(
            """insert into mytrakin.companies (tenant_id, name, kind, kinds, status)
                values (:t, 'Signfix Beta Co', 'vendor', array['vendor'], 'active')"""), {"t": t2})).scalar()
        for t, c in ((t1, c1), (t2, c2)):
            await conn.execute(text("update mytrakin.tenants set company_id = :c where id = :t"), {"c": c, "t": t})
    try:
        # Alpha's MSA is out for signature; Beta raises a counter-MSA, which is allowed
        # precisely because an unsigned copy does not count as live.
        async with get_engine().begin() as conn:
            a1 = (await conn.execute(text(
                """insert into mytrakin.agreements (tenant_id, code, kind, company_id, initiator_company_id,
                                                   tenant_side, status, effective_on)
                    values (:t, 'SIGNFIX-A-1', 'msa', :c, :me, 'supplier', 'out_for_signature', :d) returning id"""),
                {"t": t1, "c": c2, "me": c1, "d": today})).scalar()
            created.append(a1)
            a2 = (await conn.execute(text(
                """insert into mytrakin.agreements (tenant_id, code, kind, company_id, initiator_company_id,
                                                   tenant_side, status, effective_on)
                    values (:t, 'SIGNFIX-B-1', 'msa', :c, :me, 'buyer', 'pending', :d) returning id"""),
                {"t": t2, "c": c1, "me": c2, "d": today})).scalar()
            created.append(a2)

            # The signature: Alpha's MSA comes into force. This used to raise MT409.
            await conn.execute(text("update mytrakin.agreements set status = 'accepted' where id = :id"), {"id": a1})
            signed = (await conn.execute(text("select status from mytrakin.agreements where id = :id"), {"id": a1})).scalar()
            assert signed == "accepted", signed

            # The pair settles on the agreement that was signed.
            superseded = (await conn.execute(
                text("select status, decision_note from mytrakin.agreements where id = :id"), {"id": a2})).first()
            assert superseded[0] == "terminated", superseded
            assert "SIGNFIX-A-1" in superseded[1], superseded

            # A genuine second *live* MSA for the same pair is still stopped at creation.
            try:
                await conn.execute(text(
                    """insert into mytrakin.agreements (tenant_id, code, kind, company_id, initiator_company_id,
                                                       tenant_side, status, effective_on)
                        values (:t, 'SIGNFIX-C-1', 'msa', :c, :me, 'buyer', 'pending', :d)"""),
                    {"t": t2, "c": c1, "me": c2, "d": today})
                raise AssertionError("a duplicate live MSA should not be allowed")
            except Exception as e:                                    # noqa: BLE001
                assert "MT409" in str(e) or "already an active MSA" in str(e), e
    finally:
        async with get_engine().begin() as conn:
            for agreement_id in created:
                await conn.execute(text("delete from mytrakin.agreements where id = :id"), {"id": agreement_id})
            await conn.execute(text("delete from mytrakin.tenants where name like 'Signfix%'"))
            await conn.execute(text("delete from mytrakin.companies where name like 'Signfix% Co'"))


async def test_msa_lifecycle_pending_accept_reject_renew_expire(client, auth, user_ids):
    admin = auth("admin")
    tenant, partner = await _counterparty(user_ids)
    cp = {**auth("finance2"), "X-Tenant-Id": tenant}
    sender = next(c for c in (await client.get("/companies", headers=admin)).json() if c["name"] == "Meridian Pharma Inc.")
    today = date.today()
    created: list[str] = []
    try:
        # Verify → NDA → MSA: the partner must have an NDA with us first.
        nda = await client.post("/agreements", headers=admin, json={
            "kind": "nda", "company_id": partner, "tenant_side": "buyer", "effective_on": str(today),
            "status": "active", "source": "manual"})
        assert nda.status_code == 201, nda.text
        created.append(nda.json()["id"])

        # 1. Sent → pending, and the partner sees it waiting for an answer.
        sent = await client.post(f"/companies/{sender['id']}/msas", headers=admin, json={
            "counterparty_company_id": partner, "kind": "msa", "tenant_side": "supplier",
            "existing": True, "effective_on": str(today), "expires_on": str(today + timedelta(days=365))})
        assert sent.status_code == 201, sent.text
        msa_id = sent.json()["id"]
        created.append(msa_id)
        assert sent.json()["status"] == "pending", sent.text
        seen = next(a for a in (await client.get("/agreements", headers=cp)).json() if a["id"] == msa_id)
        assert seen["status"] == "pending" and seen["shared"] is True, seen

        # 2. One live MSA per pair, whichever way round: a second one is refused.
        again = await client.post(f"/companies/{sender['id']}/msas", headers=admin, json={
            "counterparty_company_id": partner, "kind": "msa", "tenant_side": "supplier",
            "existing": False, "effective_on": str(today)})
        assert again.status_code == 409 and "already an active MSA" in again.text, again.text

        # 3. Rejecting needs a note; with one it becomes rejected and the sender sees why.
        assert (await client.post(f"/agreements/{msa_id}/respond", headers=cp, json={"decision": "reject"})).status_code == 422
        rejected = await client.post(f"/agreements/{msa_id}/respond", headers=cp,
                                     json={"decision": "reject", "note": "Rates are missing from Schedule A"})
        assert rejected.status_code == 200 and rejected.json()["status"] == "rejected", rejected.text
        own = await client.get(f"/agreements/{msa_id}", headers=admin)
        assert own.json()["status"] == "rejected" and own.json()["decision_note"] == "Rates are missing from Schedule A", own.text

        # 4. A rejected MSA no longer blocks a new one. Sent again → accepted.
        sent2 = await client.post(f"/companies/{sender['id']}/msas", headers=admin, json={
            "counterparty_company_id": partner, "kind": "msa", "tenant_side": "supplier",
            "existing": False, "effective_on": str(today), "expires_on": str(today + timedelta(days=365))})
        assert sent2.status_code == 201 and sent2.json()["status"] == "pending", sent2.text
        msa_id = sent2.json()["id"]
        created.append(msa_id)
        accepted = await client.post(f"/agreements/{msa_id}/respond", headers=cp, json={"decision": "accept"})
        assert accepted.status_code == 200 and accepted.json()["status"] == "accepted", accepted.text
        assert (await client.get(f"/agreements/{msa_id}", headers=admin)).json()["status"] == "accepted"
        # Answering twice is refused.
        assert (await client.post(f"/agreements/{msa_id}/respond", headers=cp, json={"decision": "accept"})).status_code == 409

        # 5. Renewal: the sender asks; the partner declines (note required), then the partner asks and the sender accepts.
        renewal = await client.post(f"/agreements/{msa_id}/renewals", headers=admin, json={
            "expires_on": str(today + timedelta(days=700)), "note": "Keep the same scope"})
        assert renewal.status_code == 201, renewal.text
        rid = renewal.json()["id"]
        assert (await client.post(f"/agreements/renewals/{rid}/respond", headers=cp, json={"decision": "decline"})).status_code == 422
        declined = await client.post(f"/agreements/renewals/{rid}/respond", headers=cp,
                                     json={"decision": "decline", "note": "Budget frozen this year"})
        assert declined.status_code == 200, declined.text
        detail = (await client.get(f"/agreements/{msa_id}", headers=admin)).json()
        assert detail["renewals"][0]["status"] == "declined" and detail["renewals"][0]["decision_note"] == "Budget frozen this year", detail
        assert detail["expires_on"] == str(today + timedelta(days=365)), detail        # unchanged
        # The partner can ask for a renewal too; the sender accepts and the end date moves.
        asked = await client.post(f"/agreements/{msa_id}/renewals", headers=cp, json={"expires_on": str(today + timedelta(days=800))})
        assert asked.status_code == 201, asked.text
        assert (await client.post(f"/agreements/renewals/{asked.json()['id']}/respond", headers=cp, json={"decision": "accept"})).status_code == 403
        assert (await client.post(f"/agreements/renewals/{asked.json()['id']}/respond", headers=admin, json={"decision": "accept"})).status_code == 200
        assert (await client.get(f"/agreements/{msa_id}", headers=admin)).json()["expires_on"] == str(today + timedelta(days=800))

        # 6. Past its end date it becomes expired (the daily job does this; run it directly here).
        async with get_engine().begin() as conn:
            await conn.execute(text("update mytrakin.agreements set expires_on = current_date - 1 where id = :id"), {"id": msa_id})
            await conn.execute(text("select mytrakin.expire_master_agreements()"))
        expired = (await client.get(f"/agreements/{msa_id}", headers=admin)).json()
        assert expired["status"] == "expired", expired
        # 7. An expired MSA renews: the partner asks, the sender accepts → in force again with the new end date.
        back = await client.post(f"/agreements/{msa_id}/renewals", headers=cp, json={"expires_on": str(today + timedelta(days=900))})
        assert back.status_code == 201, back.text
        assert (await client.post(f"/agreements/renewals/{back.json()['id']}/respond", headers=admin, json={"decision": "accept"})).status_code == 200
        revived = (await client.get(f"/agreements/{msa_id}", headers=admin)).json()
        assert revived["status"] == "accepted" and revived["expires_on"] == str(today + timedelta(days=900)), revived
    finally:
        async with get_engine().begin() as conn:
            for agreement_id in created:
                await conn.execute(text("delete from mytrakin.agreements where id = :id"), {"id": agreement_id})
            await conn.execute(text("delete from mytrakin.tenants where id = :id"), {"id": tenant})


async def _insert_one(statement: str, **params):
    """One row from an INSERT .. RETURNING (avoids .scalar(), which some asyncpg builds
    close before the row is read)."""
    async with get_engine().begin() as conn:
        rows = (await conn.execute(text(statement), params)).mappings().all()
    return rows[0] if rows else None


async def test_nda_gate_sees_the_nda_between_the_two_companies(client, auth, user_ids):
    """The NDA gate must look at the two companies, not at one side of the link.

    Regression: an NDA is stored with the *other* party in company_id. Starting the MSA
    from that company's page (with our main company as the counterparty) made the old check
    ask for an NDA whose company_id was our own company, find none, and tell the user to
    disable Require NDA - while the NDA between the two companies was active all along.
    """
    today = date.today()
    created: list[str] = []
    t1 = (await _insert_one("insert into mytrakin.tenants (name, status) values ('Nda Pair Alpha', 'active') returning id"))["id"]
    own = (await _insert_one("""insert into mytrakin.companies (tenant_id, name, kind, kinds, status)
                                values (:t, 'Nda Pair Alpha Co', 'vendor', array['vendor'], 'active') returning id""",
                             t=t1))["id"]
    partner = (await _insert_one("""insert into mytrakin.companies (tenant_id, name, kind, kinds, status)
                                    values (:t, 'Nda Pair Beta Co', 'vendor', array['vendor'], 'active') returning id""",
                                 t=t1))["id"]
    stranger = (await _insert_one("""insert into mytrakin.companies (tenant_id, name, kind, kinds, status)
                                     values (:t, 'Nda Pair Gamma Co', 'vendor', array['vendor'], 'active') returning id""",
                                  t=t1))["id"]
    async with get_engine().begin() as conn:
        await conn.execute(text("update mytrakin.tenants set company_id = :c where id = :t"), {"c": own, "t": t1})
        await conn.execute(text("""insert into mytrakin.memberships (tenant_id, user_id, role, status)
                                   values (:t, :u, 'tenant_admin', 'active')"""),
                           {"t": t1, "u": user_ids["finance2"]})
    headers = {**auth("finance2"), "X-Tenant-Id": str(t1)}
    try:
        nda = await client.post("/agreements", headers=headers, json={
            "kind": "nda", "company_id": str(partner), "tenant_side": "supplier", "effective_on": str(today),
            "status": "active", "source": "manual"})
        assert nda.status_code == 201, nda.text
        created.append(nda.json()["id"])

        # Started from the partner's page, our own company as the counterparty (the NDA is in
        # the other column). Before the fix this returned 409 nda_required.
        msa = await client.post(f"/companies/{partner}/msas", headers=headers, json={
            "counterparty_company_id": str(own), "kind": "msa", "tenant_side": "supplier", "existing": True,
            "effective_on": str(today), "expires_on": str(today + timedelta(days=365))})
        assert msa.status_code == 201, msa.text
        created.append(msa.json()["id"])

        # A company the NDA does not cover is still stopped.
        blocked = await client.post(f"/companies/{stranger}/msas", headers=headers, json={
            "counterparty_company_id": str(own), "kind": "msa", "tenant_side": "supplier", "existing": True,
            "effective_on": str(today)})
        assert blocked.status_code == 409 and "nda_required" in blocked.text, blocked.text
    finally:
        async with get_engine().begin() as conn:
            for agreement_id in created:
                await conn.execute(text("delete from mytrakin.agreements where id = :id"), {"id": agreement_id})
            await conn.execute(text("delete from mytrakin.tenants where id = :id"), {"id": t1})
            await conn.execute(text("delete from mytrakin.companies where name like 'Nda Pair%Co'"))
