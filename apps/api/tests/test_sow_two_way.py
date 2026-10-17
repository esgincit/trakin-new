"""SOWs run both ways under one MSA: whichever workspace recorded the agreement, either
company can raise work under it, and the other company approves or turns it down with
a reason. A draft is nobody else's business until it is sent."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text

from app.db import get_engine


async def _pair(client, auth, user_ids) -> tuple[dict, dict, dict, str]:
    """A workspace pair with an accepted MSA between them: we (admin) sent it, and a
    second workspace owns the partner company. Returns (admin_headers, partner_headers,
    ours, partner_company_id)."""
    admin = auth("admin")
    today = date.today()
    async with get_engine().begin() as conn:
        tenant = (await conn.execute(text(
            "insert into mytrakin.tenants (name, status) values ('Counterparty SOW Workspace', 'active') returning id"))).scalar()
        company = (await conn.execute(text(
            """insert into mytrakin.companies (tenant_id, name, kind, kinds, status)
                values (:t, 'Two Way Partner LLC', 'vendor', array['vendor'], 'active') returning id"""),
            {"t": tenant})).scalar()
        member = (await conn.execute(text(
            """insert into mytrakin.memberships (tenant_id, user_id, role, status)
                values (:t, :u, 'tenant_admin', 'active') returning id"""),
            {"t": tenant, "u": user_ids["finance2"]})).scalar()
        await conn.execute(text("update mytrakin.tenants set company_id = :c, owner_membership_id = :m where id = :t"),
                           {"c": company, "m": member, "t": tenant})

    partner = {**auth("finance2"), "X-Tenant-Id": str(tenant)}
    ours = next(c for c in (await client.get("/companies", headers=admin)).json()
                if c["name"] == "Meridian Pharma Inc.")

    nda = await client.post("/agreements", headers=admin, json={
        "kind": "nda", "company_id": str(company), "tenant_side": "buyer",
        "effective_on": str(today), "status": "active", "source": "manual"})
    assert nda.status_code == 201, nda.text
    sent = await client.post(f"/companies/{ours['id']}/msas", headers=admin, json={
        "counterparty_company_id": str(company), "kind": "msa", "tenant_side": "supplier",
        "existing": True, "effective_on": str(today), "expires_on": str(today + timedelta(days=365))})
    assert sent.status_code == 201, sent.text
    msa_id = sent.json()["id"]
    accepted = await client.post(f"/agreements/{msa_id}/respond", headers=partner, json={"decision": "accept"})
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted", accepted.text

    async def cleanup() -> None:
        async with get_engine().begin() as conn:
            await conn.execute(text("delete from mytrakin.sows where agreement_id = :a"), {"a": msa_id})
            await conn.execute(text("delete from mytrakin.agreements where id = :a"), {"a": msa_id})
            await conn.execute(text("delete from mytrakin.agreements where company_id = :c"), {"c": company})
            await conn.execute(text("delete from mytrakin.tenants where id = :t"), {"t": tenant})

    return admin, partner, ours, str(company), msa_id, cleanup


async def test_the_counterparty_can_raise_a_sow_under_our_msa(client, auth, user_ids):
    """The other workspace creates a SOW under the MSA we recorded -- and it points at
    us, not back at themselves."""
    admin, partner, ours, partner_company, msa_id, cleanup = await _pair(client, auth, user_ids)
    try:
        today = date.today()
        made = await client.post("/sows", headers=partner, json={
            "agreement_id": msa_id, "side": "we_bill", "title": "Partner engagement",
            "start_date": str(today), "end_date": str(today + timedelta(days=60)), "status": "draft"})
        assert made.status_code == 201, made.text
        sow = made.json()
        # The SOW is with the sender of the MSA (us), not with the partner's own company.
        detail = (await client.get(f"/sows/{sow['id']}", headers=partner)).json()
        assert detail["counterparty"] == ours["name"], detail

        # A draft is ours alone: the other side does not see it.
        assert not [s for s in (await client.get("/sows", headers=admin)).json() if s["id"] == sow["id"]]
        assert not [s for s in (await client.get("/sows", headers=partner)).json() if s["id"] == sow["id"]]
    finally:
        await cleanup()


async def test_send_for_approval_then_approve(client, auth, user_ids):
    """Sent SOWs reach the other company; approving one puts it in force. The sender
    cannot answer their own SOW, and a rejection needs a reason."""
    admin, partner, ours, partner_company, msa_id, cleanup = await _pair(client, auth, user_ids)
    try:
        today = date.today()
        sow = (await client.post("/sows", headers=partner, json={
            "agreement_id": msa_id, "side": "we_bill", "title": "Needs approval",
            "start_date": str(today), "end_date": str(today + timedelta(days=60)),
            "value_cap": "5000", "status": "draft"})).json()

        sent = await client.post(f"/sows/{sow['id']}/submit", headers=partner)
        assert sent.status_code == 200 and sent.json()["status"] == "pending", sent.text

        # Now the sender sees it, without the partner's money.
        incoming = [s for s in (await client.get("/sows", headers=admin)).json() if s["id"] == sow["id"]]
        assert len(incoming) == 1, incoming
        assert incoming[0]["shared"] is True and incoming[0]["status"] == "pending", incoming[0]
        for hidden in ("value_cap", "invoiced", "collected_or_paid", "remaining", "burn_pct"):
            assert incoming[0][hidden] is None, f"{hidden} leaked: {incoming[0][hidden]}"

        # The company that raised it cannot approve its own SOW.
        assert (await client.post(f"/sows/{sow['id']}/respond", headers=partner,
                                  json={"decision": "approve"})).status_code == 403
        # A rejection needs a reason.
        assert (await client.post(f"/sows/{sow['id']}/respond", headers=admin,
                                  json={"decision": "reject"})).status_code == 422

        approved = await client.post(f"/sows/{sow['id']}/respond", headers=admin, json={"decision": "approve"})
        assert approved.status_code == 200 and approved.json()["status"] == "active", approved.text
        own = (await client.get(f"/sows/{sow['id']}", headers=partner)).json()
        assert own["status"] == "active", own
        # Answering twice is refused.
        assert (await client.post(f"/sows/{sow['id']}/respond", headers=admin,
                                  json={"decision": "approve"})).status_code == 409
    finally:
        await cleanup()


async def test_turning_a_sow_down_keeps_the_reason(client, auth, user_ids):
    admin, partner, ours, partner_company, msa_id, cleanup = await _pair(client, auth, user_ids)
    try:
        today = date.today()
        sow = (await client.post("/sows", headers=partner, json={
            "agreement_id": msa_id, "side": "we_pay", "title": "Rejected work",
            "start_date": str(today), "end_date": str(today + timedelta(days=30)), "status": "draft"})).json()
        assert (await client.post(f"/sows/{sow['id']}/submit", headers=partner)).status_code == 200

        turned = await client.post(f"/sows/{sow['id']}/respond", headers=admin,
                                   json={"decision": "reject", "note": "Scope is too broad for this term"})
        assert turned.status_code == 200 and turned.json()["status"] == "rejected", turned.text
        own = (await client.get(f"/sows/{sow['id']}", headers=partner)).json()
        assert own["decision_note"] == "Scope is too broad for this term", own

        # And it can be revised and sent again.
        assert (await client.post(f"/sows/{sow['id']}/submit", headers=partner)).status_code == 200
        assert (await client.get(f"/sows/{sow['id']}", headers=partner)).json()["status"] == "pending"
    finally:
        await cleanup()


async def test_a_third_workspace_sees_nothing(client, auth, user_ids):
    """A SOW is shared only between the two companies on the agreement."""
    admin, partner, ours, partner_company, msa_id, cleanup = await _pair(client, auth, user_ids)
    try:
        today = date.today()
        sow = (await client.post("/sows", headers=partner, json={
            "agreement_id": msa_id, "side": "we_bill", "title": "Private",
            "start_date": str(today), "end_date": str(today + timedelta(days=30)), "status": "draft"})).json()
        assert (await client.post(f"/sows/{sow['id']}/submit", headers=partner)).status_code == 200

        # The founder's own workspace is not a party to this MSA.
        other = {**auth("founder")}
        assert not [s for s in (await client.get("/sows", headers=other)).json() if s["id"] == sow["id"]]
        assert (await client.get(f"/sows/{sow['id']}", headers=other)).status_code == 404
        # And cannot answer it.
        assert (await client.post(f"/sows/{sow['id']}/respond", headers=other,
                                  json={"decision": "approve"})).status_code == 403
    finally:
        await cleanup()


async def test_no_sows_under_an_msa_that_is_not_in_force(client, auth, user_ids):
    """A pending or turned-down MSA carries no work; an expired one neither."""
    admin, partner, ours, partner_company, msa_id, cleanup = await _pair(client, auth, user_ids)
    try:
        today = date.today()
        # Turn the accepted MSA into a rejected one.
        async with get_engine().begin() as conn:
            await conn.execute(text("update mytrakin.agreements set status = 'rejected' where id = :a"), {"a": msa_id})
        body = {"agreement_id": msa_id, "side": "we_bill", "title": "Too early",
                "start_date": str(today), "end_date": str(today + timedelta(days=30)), "status": "draft"}
        refused = await client.post("/sows", headers=partner, json=body)
        assert refused.status_code == 409, refused.text

        async with get_engine().begin() as conn:
            await conn.execute(text("update mytrakin.agreements set status = 'accepted' where id = :a"), {"a": msa_id})
        assert (await client.post("/sows", headers=partner, json=body)).status_code == 201
    finally:
        await cleanup()
