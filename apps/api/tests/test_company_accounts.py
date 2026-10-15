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
    blocked = await client.get("/invoices", headers=h)
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
