"""Work across two workspaces under one MSA (Strike T011303-1049, T011303-1047).

An MSA lives in the workspace that sent it. The company that received and accepted it
must still count it as active (project gate), and must be able to place its own people
on a project the sender assigned to it by SOW."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text

from app.db import get_engine
from tests.test_sow_two_way import _pair


async def _no_nda_gate(partner_tenant: str) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(text("""update mytrakin.tenants
                                      set settings = jsonb_set(coalesce(settings, '{}'), '{workflow}', '{"requireNDA": false}')
                                    where id = :t"""), {"t": partner_tenant})


async def test_an_msa_we_received_lets_us_activate_a_project(client, auth, user_ids):
    """T011303-1049: the receiving company was told 'no active MSA' although it had accepted one."""
    admin, partner, ours, partner_company, msa_id, cleanup = await _pair(client, auth, user_ids)
    try:
        await _no_nda_gate(partner["X-Tenant-Id"])
        # Both sides are offered the other company as client / prime (it isn't in their own company list).
        assert ours["id"] in [c["id"] for c in (await client.get("/projects/counterparties", headers=partner)).json()]
        theirs = (await client.get("/projects/counterparties", headers=admin)).json()
        assert partner_company in [c["id"] for c in theirs] and ours["id"] not in [c["id"] for c in theirs], theirs
        made = await client.post("/projects", headers=partner, json={
            "name": "Work for the MSA sender", "client_company_id": ours["id"], "status": "active"})
        assert made.status_code == 201, made.text

        # The gate still bites when the MSA is not in force.
        async with get_engine().begin() as conn:
            await conn.execute(text("update mytrakin.agreements set status = 'rejected' where id = :a"), {"a": msa_id})
        refused = await client.post("/projects", headers=partner, json={
            "name": "No MSA any more", "client_company_id": ours["id"], "status": "active"})
        assert refused.status_code == 409 and refused.json()["error"]["code"] == "msa_required", refused.text
    finally:
        await cleanup()


async def test_a_project_assigned_to_us_by_sow_can_take_a_placement(client, auth, user_ids):
    """T011303-1047: the sender's project shows in our placement picker; placing someone makes our own copy."""
    admin, partner, ours, partner_company, msa_id, cleanup = await _pair(client, auth, user_ids)
    today = date.today()
    project = None
    try:
        await _no_nda_gate(partner["X-Tenant-Id"])
        project = (await client.post("/projects", headers=admin, json={"name": "Assigned Rollout", "status": "active"})).json()
        sow = (await client.post("/sows", headers=admin, json={
            "agreement_id": msa_id, "side": "we_pay", "title": "Vendor work order", "project_id": project["id"],
            "start_date": str(today), "end_date": str(today + timedelta(days=90)), "status": "draft"})).json()

        # A draft SOW assigns nothing yet.
        assert not [p for p in (await client.get("/projects/shared", headers=partner)).json() if p["id"] == project["id"]]
        assert (await client.post(f"/sows/{sow['id']}/submit", headers=admin)).status_code == 200

        shared = [p for p in (await client.get("/projects/shared", headers=partner)).json() if p["id"] == project["id"]]
        assert len(shared) == 1 and shared[0]["assigned_by"] == ours["name"] and shared[0]["local_project_id"] is None, shared
        # A third workspace sees nothing.
        third = await client.get("/projects/shared", headers=auth("founder"))
        assert third.status_code == 403 or not [p for p in third.json() if p["id"] == project["id"]], third.text

        async with get_engine().begin() as conn:
            consultant = str((await conn.execute(text(
                """insert into mytrakin.consultants (tenant_id, full_name, email, engagement, status, start_date)
                   values (:t, 'Placed Person', 'placed.person@example.com', 'w2_contract', 'active', current_date)
                   returning id"""), {"t": partner["X-Tenant-Id"]})).scalar())
        body = {"consultant_id": consultant, "project_id": project["id"], "start_date": str(today)}
        first = await client.post("/placements", headers=partner, json=body)
        assert first.status_code == 201, first.text
        local = first.json()["project_id"]
        assert local != project["id"] and first.json()["ar_company_id"] == ours["id"], first.json()

        copy = (await client.get(f"/projects/{local}", headers=partner)).json()
        assert copy["name"] == "Assigned Rollout" and copy["prime_company_id"] == ours["id"], copy
        # Picked again: the same copy, not a second one.
        again = await client.post("/placements", headers=partner, json={**body, "role_title": "Second"})
        assert again.status_code == 201 and again.json()["project_id"] == local, again.text
        listed = [p for p in (await client.get("/projects/shared", headers=partner)).json() if p["id"] == project["id"]]
        assert listed[0]["local_project_id"] == local, listed
    finally:
        await cleanup()
        if project:
            async with get_engine().begin() as conn:
                await conn.execute(text("delete from mytrakin.projects where id = :p"), {"p": project["id"]})
