"""Owner builds roles: F1 finance view-only, F2 finance full; per-user exceptions; owner only."""

from sqlalchemy import text

from app.db import get_engine


async def _member(tenant_id, user_id, role="finance"):
    async with get_engine().begin() as conn:
        return (await conn.execute(text(
            """insert into mytrakin.memberships (tenant_id, user_id, role, status) values (:t, :u, :r, 'active')
               on conflict (tenant_id, user_id) where user_id is not null do update set role = excluded.role
               returning id"""), {"t": tenant_id, "u": user_id, "r": role})).scalar()


async def test_f1_read_only_f2_read_write(client, auth, user_ids):
    admin = auth("admin")                                    # demo owner (earliest active tenant_admin)
    s = (await client.get("/session", headers=admin)).json()
    assert s["is_owner"] is True
    await _member(s["tenant"]["id"], user_ids["finance2"])
    role = await client.post("/roles", headers=admin, json={
        "name": "Finance – view only", "base_role": "finance",
        "permissions": {"invoices": "read", "pay": "read", "users": "none"}})
    assert role.status_code == 201, role.text
    assert (await client.post("/roles", headers=admin, json={
        "name": "finance – VIEW only", "base_role": "finance"})).status_code == 409      # names are unique
    f1 = (await client.get("/session", headers=auth("finance"))).json()["membership_id"]
    f1h, f2h = auth("finance"), auth("finance2")
    try:
        assert (await client.patch(f"/users/{f1}/access", headers=admin,
                                   json={"custom_role_id": role.json()["id"]})).status_code == 200
        assert (await client.get("/invoices?direction=ar", headers=f1h)).status_code == 200    # can read
        w1 = await client.post("/invoices", headers=f1h, json={})
        assert w1.status_code == 403 and w1.json()["error"]["code"] == "no_permission"
        assert "view-only" in w1.json()["error"]["message"]
        assert (await client.post("/invoices", headers=f2h, json={})).status_code == 422  # F2 gets to validation
        hidden = await client.get("/users", headers=f1h)
        assert hidden.status_code == 403 and "don't have access" in hidden.json()["error"]["message"]
        s1 = (await client.get("/session", headers=f1h)).json()
        assert s1["permissions"]["invoices"] == "read" and s1["custom_role"] == "Finance – view only"
        # a per-person exception beats the role
        assert (await client.patch(f"/users/{f1}/access", headers=admin,
                                   json={"permission_overrides": {"invoices": "write"}})).status_code == 200
        assert (await client.post("/invoices", headers=f1h, json={})).status_code == 422
        # editing the role changes everyone on it
        await client.patch(f"/roles/{role.json()['id']}", headers=admin, json={"permissions": {"timesheets": "none"}})
        assert (await client.get("/timesheets", headers=f1h)).status_code == 403
        roles = (await client.get("/roles", headers=admin)).json()
        assert {m["key"] for m in roles["modules"]} >= {"invoices", "users", "timesheets"}
        assert next(r for r in roles["roles"] if r["id"] == role.json()["id"])["members"] == 1
    finally:
        await client.patch(f"/users/{f1}/access", headers=admin, json={"custom_role_id": None, "permission_overrides": {}})
        await client.delete(f"/roles/{role.json()['id']}", headers=admin)
    assert (await client.post("/invoices", headers=f1h, json={})).status_code == 422          # back to full access


async def test_only_owner_manages_roles_and_input_is_validated(client, auth):
    assert (await client.get("/roles", headers=auth("finance"))).status_code == 403
    assert (await client.post("/roles", headers=auth("finance"), json={"name": "X role", "base_role": "finance"})).status_code == 403
    for perms in ({"invoices": "maybe"}, {"invoicez": "read"}):
        r = await client.post("/roles", headers=auth("admin"), json={"name": "Bad", "base_role": "finance", "permissions": perms})
        assert r.status_code == 422, r.text
    me = (await client.get("/session", headers=auth("admin"))).json()["membership_id"]
    assert (await client.patch(f"/users/{me}/access", headers=auth("admin"),
                               json={"permission_overrides": {"users": "none"}})).status_code == 400   # owner keeps full access
