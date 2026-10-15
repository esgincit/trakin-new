"""MFA is the user's choice: nobody is forced; once someone turns it on, an aal1 token is refused."""

from sqlalchemy import text

from app.db import get_engine


async def test_finance_and_admins_are_not_forced_into_mfa(client, auth):
    assert (await client.get("/dashboard", headers=auth("finance", aal="aal1"))).status_code == 200
    assert (await client.get("/session", headers=auth("admin", aal="aal1"))).status_code == 200


async def test_mfa_on_requires_the_second_step(client, auth, user_ids):
    async with get_engine().begin() as conn:
        await conn.execute(text("insert into auth.mfa_factors (user_id, status) values (:u, 'verified')"),
                           {"u": user_ids["consultant"]})
    try:
        r = await client.get("/session", headers=auth("consultant", aal="aal1"))
        assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_required"
        assert (await client.get("/session", headers=auth("consultant", aal="aal2"))).status_code == 200
        assert (await client.get("/me", headers=auth("consultant", aal="aal1"))).status_code == 403
        users = (await client.get("/users", headers=auth("admin"))).json()
        assert next(u for u in users if u["email"] == "ravi.kumar@example.com")["mfa_on"] is True
    finally:
        async with get_engine().begin() as conn:
            await conn.execute(text("delete from auth.mfa_factors where user_id = :u"), {"u": user_ids["consultant"]})


async def test_unverified_factor_does_not_lock_anyone_out(client, auth, user_ids):
    async with get_engine().begin() as conn:
        await conn.execute(text("insert into auth.mfa_factors (user_id, status) values (:u, 'unverified')"),
                           {"u": user_ids["consultant"]})
    try:
        assert (await client.get("/session", headers=auth("consultant", aal="aal1"))).status_code == 200
    finally:
        async with get_engine().begin() as conn:
            await conn.execute(text("delete from auth.mfa_factors where user_id = :u"), {"u": user_ids["consultant"]})


async def test_owner_allocates_the_mfa_option(client, auth):
    admin = auth("admin")
    fid = (await client.get("/session", headers=auth("finance"))).json()["membership_id"]
    assert (await client.get("/me", headers=auth("finance"))).json()["mfa_allowed"] is True
    try:
        assert (await client.patch(f"/users/{fid}", headers=admin, json={"mfa_allowed": False})).status_code == 200
        assert (await client.get("/me", headers=auth("finance"))).json()["mfa_allowed"] is False
        users = (await client.get("/users", headers=admin)).json()
        assert next(u for u in users if u["id"] == fid)["mfa_allowed"] is False
    finally:
        await client.patch(f"/users/{fid}", headers=admin, json={"mfa_allowed": True})
