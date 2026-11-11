"""Sign-in, account and company-status rules."""

from __future__ import annotations

from sqlalchemy import text

from app.db import get_engine
from tests.test_company_onboarding import _new_company


async def _tenant_of(user_ids, who="admin"):
    async with get_engine().begin() as conn:
        return (await conn.execute(text("select tenant_id from mytrakin.memberships where user_id = :u and status = 'active' limit 1"),
                                   {"u": user_ids[who]})).scalar()


async def _set_status(tid, status):
    async with get_engine().begin() as conn:
        await conn.execute(text("update mytrakin.tenants set status = :s where id = :t"), {"s": status, "t": tid})


async def test_suspended_company_can_read_but_not_change(client, auth, user_ids):
    tid = await _tenant_of(user_ids)
    await _set_status(tid, "suspended")
    try:
        read = await client.get("/session", headers=auth("admin"))
        assert read.status_code == 200, read.text
        write = await client.post("/invoices", headers=auth("admin"), json={})
        assert write.status_code == 403 and write.json()["error"]["code"] == "company_suspended", write.text
        assert "suspended" in write.json()["error"]["message"]
    finally:
        await _set_status(tid, "active")
    again = await client.post("/invoices", headers=auth("admin"), json={})
    assert again.status_code == 422 or again.json()["error"]["code"] != "company_suspended", again.text


async def test_invites_claimed_only_after_email_is_confirmed():
    email = "late.confirm@invite.example"
    async with get_engine().begin() as conn:
        tid = (await conn.execute(text("select id from mytrakin.tenants limit 1"))).scalar()
        await conn.execute(text("insert into mytrakin.memberships (tenant_id, invited_email, role) values (:t, :e, 'viewer')"),
                           {"t": tid, "e": email})
        uid = (await conn.execute(text("insert into auth.users (email, email_confirmed_at) values (:e, null) returning id"),
                                  {"e": email})).scalar()
        claimed = lambda: conn.execute(text("select user_id from mytrakin.memberships where invited_email = :e"), {"e": email})
        assert (await claimed()).scalar() is None
        await conn.execute(text("update auth.users set email_confirmed_at = now() where id = :u"), {"u": uid})
        assert (await claimed()).scalar() == uid
        await conn.execute(text("delete from mytrakin.memberships where invited_email = :e"), {"e": email})
        await conn.execute(text("delete from auth.users where id = :u"), {"u": uid})


async def test_confirmed_signup_claims_invite_at_once():
    email = "already.confirmed@invite.example"
    async with get_engine().begin() as conn:
        tid = (await conn.execute(text("select id from mytrakin.tenants limit 1"))).scalar()
        await conn.execute(text("insert into mytrakin.memberships (tenant_id, invited_email, role) values (:t, :e, 'viewer')"),
                           {"t": tid, "e": email})
        uid = (await conn.execute(text("insert into auth.users (email, email_confirmed_at) values (:e, now()) returning id"),
                                  {"e": email})).scalar()
        got = (await conn.execute(text("select user_id from mytrakin.memberships where invited_email = :e"), {"e": email})).scalar()
        assert got == uid
        await conn.execute(text("delete from mytrakin.memberships where invited_email = :e"), {"e": email})
        await conn.execute(text("delete from auth.users where id = :u"), {"u": uid})


async def test_company_admin_cannot_demote_or_remove_an_owner(client, auth, user_ids):
    cid = (await _new_company(client, auth))["id"]
    owner = await client.post(f"/companies/{cid}/members", headers=auth("admin"),
                              json={"email": "finance@example.com", "company_role": "owner"})
    assert owner.status_code == 201, owner.text
    async with get_engine().begin() as conn:
        tenant = (await conn.execute(text("select tenant_id from mytrakin.companies where id = :c"), {"c": cid})).scalar()
        await conn.execute(text("""insert into mytrakin.company_members (tenant_id, company_id, user_id, company_role, status)
                                   values (:t, :c, :u, 'admin', 'active')"""), {"t": tenant, "c": cid, "u": user_ids["finance2"]})
    h = auth("finance2")
    mid = owner.json()["id"]
    assert (await client.patch(f"/companies/{cid}/members/{mid}", headers=h, json={"company_role": "member"})).status_code == 403
    assert (await client.delete(f"/companies/{cid}/members/{mid}", headers=h)).status_code == 403
    # An owner (the creator, super admin) still can.
    assert (await client.patch(f"/companies/{cid}/members/{mid}", headers=auth("admin"), json={"company_role": "member"})).status_code == 200
