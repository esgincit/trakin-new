"""One company = one account: anyone creates a company → it waits for the platform admin →
activated → the creator owns it and can hand ownership on."""

from __future__ import annotations

from sqlalchemy import text

from app.db import get_engine
from tests.test_company_onboarding import w9_pdf


async def _founder_company(client, auth, n: int, ein: str) -> dict:
    """Founder (no company yet) runs the full US wizard. Returns {tenant_id, company_id, headers, ...}."""
    h = auth("founder")
    started = await client.post("/onboarding/accounts", headers=h, json={"country": "US"})
    assert started.status_code == 201, started.text
    tid, sid = started.json()["tenant_id"], started.json()["id"]
    h = {**h, "X-Tenant-Id": tid}
    up = await client.post(f"/onboarding/sessions/{sid}/w9", headers=h,
                           files={"file": ("w9.pdf", w9_pdf(ein, f"Founder {n} Staffing LLC"), "application/pdf")})
    assert up.status_code == 200, up.text
    d = await client.patch(f"/onboarding/sessions/{sid}", headers=h, json={
        "kind": "vendor", "domain": f"founder{n}.example", "company_email": f"ops@founder{n}.example",
        "dba": "Founder", "ein": ein})
    assert d.status_code == 200, d.text
    code = (await client.post(f"/onboarding/sessions/{sid}/email-code", headers=h, json={})).json()
    assert "test_code" in code, code
    assert (await client.post(f"/onboarding/sessions/{sid}/email-verify", headers=h,
                              json={"code": code["test_code"]})).status_code == 200
    done = await client.post(f"/onboarding/sessions/{sid}/complete", headers=h, json={"authorized": True})
    assert done.status_code == 201, done.text
    return {**done.json(), "tenant_id": tid, "headers": h}


async def test_new_user_creates_company_pending_activation(client, auth):
    acct = await _founder_company(client, auth, 1, "31-4159261")
    h = acct["headers"]
    s = (await client.get("/session", headers=h)).json()
    assert s["role"] == "tenant_admin" and s["is_owner"] is True
    assert s["tenant"]["status"] == "onboarding" and s["tenant"]["name"] == "Founder 1 Staffing LLC"
    assert s["tenant"]["company_id"] == str(acct["company_id"])
    blocked = await client.get("/consultants", headers=h)
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "pending_activation"
    assert (await client.get(f"/companies/{acct['company_id']}", headers=h)).status_code == 200
    own = await client.post(f"/companies/{acct['company_id']}/activate", headers=h)
    assert own.status_code == 403            # only the platform activates the company itself


async def test_pending_company_limit(client, auth, user_ids):
    h = auth("founder")
    try:
        codes = [(await client.post("/onboarding/accounts", headers=h, json={"country": "US"})).status_code
                 for _ in range(4)]
        assert 429 in codes and codes[0] == 201
        r = await client.post("/onboarding/accounts", headers=h, json={"country": "US"})
        assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_pending"
    finally:
        async with get_engine().begin() as conn:   # drafts without a company profile
            await conn.execute(text(
                """delete from mytrakin.tenants t using mytrakin.memberships m
                    where m.id = t.owner_membership_id and m.user_id = :u
                      and t.company_id is null and t.status = 'onboarding'"""), {"u": user_ids["founder"]})


async def test_platform_activates_company_and_owner_gets_in(client, auth):
    acct = await _founder_company(client, auth, 2, "27-1828182")
    p = auth("platform")
    assert (await client.get("/platform/companies?status=pending", headers=auth("admin"))).status_code == 403
    queue = (await client.get("/platform/companies?status=pending", headers=p)).json()
    row = next(r for r in queue if r["tenant_id"] == acct["tenant_id"])
    assert row["name"] == "Founder 2 Staffing LLC" and row["owner_email"] == "founder@newco.example"
    detail = (await client.get(f"/platform/companies/{acct['tenant_id']}", headers=p)).json()
    assert detail["company"]["w9_status"] == "submitted" and "checks" in detail
    assert detail["w9_url"]                                  # the reviewer can open the W-9 itself
    no_note = await client.post(f"/platform/companies/{acct['tenant_id']}/decision", headers=p, json={"decision": "needs_info"})
    assert no_note.status_code == 400
    ok = await client.post(f"/platform/companies/{acct['tenant_id']}/decision", headers=p, json={"decision": "activate"})
    assert ok.status_code == 200, ok.text
    again = await client.post(f"/platform/companies/{acct['tenant_id']}/decision", headers=p, json={"decision": "activate"})
    assert again.status_code == 409
    h = acct["headers"]
    assert (await client.get("/session", headers=h)).json()["tenant"]["status"] == "active"
    assert (await client.get("/consultants", headers=h)).status_code == 200
    assert (await client.get(f"/companies/{acct['company_id']}", headers=h)).json()["status"] == "active"
    assert acct["tenant_id"] not in [r["tenant_id"] for r in
                                     (await client.get("/platform/companies?status=pending", headers=p)).json()]


async def test_platform_rejects_company_with_a_note(client, auth):
    acct = await _founder_company(client, auth, 4, "52-6060606")
    p = auth("platform")
    r = await client.post(f"/platform/companies/{acct['tenant_id']}/decision", headers=p,
                          json={"decision": "reject", "note": "Could not verify the business"})
    assert r.status_code == 200 and r.json()["status"] == "closed"
    # a closed company is no longer reachable by its members
    assert (await client.get("/session", headers=acct["headers"])).status_code == 403


async def test_platform_admins_managed_by_platform_only(client, auth):
    p = auth("platform")
    assert (await client.get("/platform/admins", headers=auth("admin"))).status_code == 403
    assert (await client.post("/platform/admins", headers=p, json={"email": "admin@example.com"})).status_code == 201
    assert (await client.post("/platform/admins", headers=p, json={"email": "nobody@nowhere.example"})).status_code == 400
    rows = (await client.get("/platform/admins", headers=p)).json()
    me = next(a for a in rows if a["email"] == "owner@mytrakin.example")
    other = next(a for a in rows if a["email"] == "admin@example.com")
    assert (await client.delete(f"/platform/admins/{me['user_id']}", headers=p)).status_code == 400   # not yourself
    assert (await client.delete(f"/platform/admins/{other['user_id']}", headers=p)).status_code == 200
    assert (await client.get("/platform/metrics", headers=auth("admin"))).status_code == 403


async def test_owner_transfers_ownership(client, auth, user_ids):
    acct = await _founder_company(client, auth, 3, "45-9045090")
    await client.post(f"/platform/companies/{acct['tenant_id']}/decision", headers=auth("platform"),
                      json={"decision": "activate"})
    h = acct["headers"]
    async with get_engine().begin() as conn:                         # 'outsider' joins as finance
        mid = (await conn.execute(text(
            """insert into mytrakin.memberships (tenant_id, user_id, role, status)
               values (:t, :u, 'finance', 'active') returning id"""),
            {"t": acct["tenant_id"], "u": user_ids["outsider"]})).scalar()
    try:
        me = (await client.get("/session", headers=h)).json()["membership_id"]
        oh = {**auth("outsider"), "X-Tenant-Id": acct["tenant_id"]}
        assert (await client.post(f"/users/{me}/transfer-ownership", headers=oh)).status_code == 403
        assert (await client.post(f"/users/{me}/transfer-ownership", headers=h)).status_code == 400   # already owner
        moved = await client.post(f"/users/{mid}/transfer-ownership", headers=h)
        assert moved.status_code == 200, moved.text
        s_new, s_old = (await client.get("/session", headers=oh)).json(), (await client.get("/session", headers=h)).json()
        assert s_new["is_owner"] is True and s_new["role"] == "tenant_admin" and s_old["is_owner"] is False
        # the old owner (still an admin) can't demote the new owner
        demote = await client.patch(f"/users/{mid}", headers=h, json={"role": "finance"})
        assert demote.status_code == 400 and "owner" in demote.json()["error"]["message"]
        members = (await client.get(f"/companies/{acct['company_id']}/members", headers=oh)).json()
        top = [m for m in members if m["company_role"] == "super_admin"]
        assert len(top) == 1 and top[0]["email"] == "someone@else.example"
        # the platform can hand it back (owner left)
        back = await client.post(f"/platform/companies/{acct['tenant_id']}/owner", headers=auth("platform"),
                                 json={"email": "founder@newco.example"})
        assert back.status_code == 200, back.text
        assert (await client.get("/session", headers=h)).json()["is_owner"] is True
    finally:
        async with get_engine().begin() as conn:
            await conn.execute(text("delete from mytrakin.memberships where id = :m"), {"m": mid})
            await conn.execute(text("delete from mytrakin.company_members where user_id = :u"), {"u": user_ids["outsider"]})


async def test_daily_job_purges_abandoned_drafts(client):
    async with get_engine().begin() as conn:
        old = (await conn.execute(text("""insert into mytrakin.tenants (name, status, created_at)
                                            values ('Abandoned draft', 'onboarding', now() - interval '8 days') returning id"""))).scalar()
        fresh = (await conn.execute(text("""insert into mytrakin.tenants (name, status)
                                              values ('Fresh draft', 'onboarding') returning id"""))).scalar()
    r = await client.get("/cron/daily", headers={"Authorization": "Bearer cron-test-secret"})
    assert r.status_code == 200 and r.json()["purged_drafts"] >= 1
    async with get_engine().begin() as conn:
        left = {row[0] for row in (await conn.execute(text("select id from mytrakin.tenants where id in (:a, :b)"),
                                                      {"a": old, "b": fresh})).all()}
        await conn.execute(text("delete from mytrakin.tenants where id = :b"), {"b": fresh})
    assert left == {fresh}
