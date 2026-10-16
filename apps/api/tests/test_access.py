"""Who can see what: tenant isolation, roles and the AR/AP-only rule."""

from __future__ import annotations


async def test_health(client):
    assert (await client.get("/health")).json()["status"] == "ok"
    assert (await client.get("/health/db")).json()["status"] == "ok"


async def test_requires_sign_in(client):
    response = await client.get("/dashboard")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_bad_token_rejected(client):
    response = await client.get("/dashboard", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


async def test_me_lists_workspaces(client, auth):
    body = (await client.get("/me", headers=auth("admin"))).json()
    assert [t["tenant_name"] for t in body["tenants"]] == ["Executive Software Guild Inc."]
    assert body["is_platform_admin"] is False


async def test_outsider_has_no_workspace(client, auth):
    response = await client.get("/dashboard", headers=auth("outsider"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "no_access"


async def test_money_roles_work_without_mfa(client, auth):
    # Two-step verification is optional: money roles sign in with password/OTP alone.
    assert (await client.get("/dashboard", headers=auth("finance", aal="aal1"))).status_code == 200
    assert (await client.get("/session", headers=auth("consultant", aal="aal1"))).status_code == 200


async def test_session_capabilities(client, auth):
    finance = (await client.get("/session", headers=auth("finance"))).json()
    vendor = (await client.get("/session", headers=auth("vendor"))).json()
    assert finance["role"] == "finance" and finance["can"]["see_money"]
    assert vendor["role"] == "vendor_admin" and not vendor["can"]["see_bill_rate"] and vendor["can"]["see_pay_rate"]


async def test_vendor_sees_only_own_ap(client, auth):
    rows = (await client.get("/invoices", params={"direction": "ap"}, headers=auth("vendor"))).json()
    assert rows and all(r["party"] == "BrightPath Tech LLC" for r in rows)
    ar = (await client.get("/invoices", params={"direction": "ar"}, headers=auth("vendor"))).json()
    assert ar == []


async def test_vendor_never_sees_bill_rate(client, auth):
    placements = (await client.get("/placements", headers=auth("vendor"))).json()
    assert placements, "vendor should see the placements it supplies"
    assert all(p["bill_rate"] is None for p in placements)
    assert all(p["pay_rate"] is not None for p in placements)
    consultants = (await client.get("/consultants", headers=auth("vendor"))).json()
    assert [c["full_name"] for c in consultants] == ["Ravi Kumar"]


async def test_consultant_sees_status_not_money(client, auth):
    overview = (await client.get("/me/consultant", headers=auth("consultant"))).json()
    text = str(overview)
    assert "bill_rate" not in text and "pay_rate" not in text
    assert len(overview["projects"]) == 2          # works on two projects at once
    placements = (await client.get("/placements", headers=auth("consultant"))).json()
    assert all(p["bill_rate"] is None and p["pay_rate"] is None for p in placements)
    assert (await client.get("/invoices", params={"direction": "ar"}, headers=auth("consultant"))).status_code == 403


async def test_consultant_cannot_approve_own_timesheet(client, auth):
    rows = (await client.get("/me/timesheets", headers=auth("consultant"))).json()
    assert {r["project"] for r in rows} >= {"S/4 Security Rollout", "GRC Audit Support"}
    response = await client.post(f"/timesheets/{rows[0]['timesheet_id']}/approve", headers=auth("consultant"))
    assert response.status_code == 403


async def test_finance_sees_both_rates_and_tenant_only(client, auth):
    placements = (await client.get("/placements", headers=auth("finance"))).json()
    ravi = [p for p in placements if p["consultant"] == "Ravi Kumar"]
    assert {(float(p["bill_rate"]), float(p["pay_rate"])) for p in ravi} == {(95.0, 80.0), (105.0, 82.0)}
    companies = (await client.get("/companies", headers=auth("finance"))).json()
    assert len(companies) == 5


async def test_end_client_rates_are_never_stored(client, auth):
    flow = (await client.get("/payment-flow", headers=auth("finance"))).json()
    text = str(flow)
    assert "Meridian" in text                         # the end client is shown by name …
    assert "end_client_rate" not in text              # … but nothing about its money exists


async def test_platform_console_is_owner_only(client, auth):
    assert (await client.get("/platform/metrics", headers=auth("admin"))).status_code == 403
    metrics = (await client.get("/platform/metrics", headers=auth("platform"))).json()
    assert metrics["companies"]["total"] >= 1 and metrics["users"]["active_in_companies"] >= 1


async def test_new_user_without_a_workspace_can_use_the_network(client, auth):
    """A fresh Google/Microsoft sign-up has no invite yet: feed, people and posting work; workspace data stays closed."""
    h = auth("outsider")
    assert (await client.get("/network/feed", headers=h)).status_code == 200
    assert (await client.get("/network/people", headers=h)).status_code == 200
    # a workspace-only post needs a workspace …
    r = await client.post("/network/posts", headers=h, json={"body": "Hi", "kind": "update", "audience": "company"})
    assert r.status_code == 400
    # … a network-wide post does not
    r = await client.post("/network/posts", headers=h, json={"body": "Hello network", "kind": "update", "audience": "network"})
    assert r.status_code == 201
    feed = (await client.get("/network/feed", headers=h)).json()
    assert any(p["body"] == "Hello network" and p["network_wide"] for p in feed)
    assert (await client.get("/dashboard", headers=h)).status_code == 403
