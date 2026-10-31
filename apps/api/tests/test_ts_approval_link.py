"""End-client timesheet approval links.

The placed-by company approves first; the week then flows to the end client's own
myTrakIn workspace people by e-mail with a personal approval link (like e-signatures):
they review the hours, approve — which triggers automatic invoicing — or return the
week with a note. Nothing else of the end client's is exposed."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.db import get_engine
from app.utils import sha256_hex
from app.utils import week_start as sunday_of

THIS_WEEK = sunday_of(date.today())
NEXT_WEEK = THIS_WEEK + timedelta(days=7)
TOKEN = "client-approval-token-0123456789abcdefgh"


async def _linkable_client() -> tuple[str, str]:
    """A company with its own myTrakIn workspace, reachable as an end client."""
    async with get_engine().begin() as conn:
        tenant = (await conn.execute(text(
            "insert into mytrakin.tenants (name, status) values ('Approval Link Client Inc', 'active') returning id"))).scalar()
        company = (await conn.execute(text(
            """insert into mytrakin.companies (tenant_id, name, kind, kinds, status)
               values (:t, 'Approval Link Client', 'client', array['client', 'end_client'], 'active') returning id"""),
            {"t": tenant})).scalar()
        member = (await conn.execute(text(
            """insert into mytrakin.memberships (tenant_id, user_id, role, status)
               select :t, id, 'tenant_admin', 'active' from mytrakin.profiles where email = 'admin@example.com'
               returning id"""), {"t": tenant})).scalar()
        await conn.execute(text(
            "update mytrakin.tenants set company_id = :c, owner_membership_id = :m where id = :t"),
            {"c": company, "m": member, "t": tenant})
        return str(tenant), str(company)


async def _esg_tenant() -> str:
    async with get_engine().begin() as conn:
        return str((await conn.execute(text(
            "select id from mytrakin.tenants where name like 'Executive Software Guild%' limit 1"))).scalar())


async def _submitted_week(client, company: str, week: date) -> tuple[str, str]:
    """A fresh consultant + placement billed to Northwind (active MSA), end client = our
    linkable company, and a submitted week of 10 hours."""
    async with get_engine().begin() as conn:
        esg = (await conn.execute(text(
            "select id from mytrakin.tenants where name like 'Executive Software Guild%' limit 1"))).scalar()
        northwind = (await conn.execute(text(
            "select id from mytrakin.companies where name = 'Northwind Consulting'"))).scalar()
        project = (await conn.execute(text(
            "select id from mytrakin.projects where tenant_id = :t and status = 'active' limit 1"), {"t": esg})).scalar()
        cid = (await conn.execute(text(
            """insert into mytrakin.consultants (tenant_id, full_name, email, engagement, status, start_date)
               values (:t, 'Link Client Person', 'link.client@example.com', 'w2_contract', 'active', current_date - 30)
               returning id"""), {"t": esg})).scalar()
        pid = (await conn.execute(text(
            """insert into mytrakin.placements (tenant_id, consultant_id, project_id, role_title, start_date,
                          hours_per_week, end_client_company_id, ar_company_id, bill_rate, ar_terms, status)
               values (:t, :c, :p, 'Engineer', current_date - 30, 40, :ec, :ar, 60, 'Net 30', 'active') returning id"""),
            {"t": esg, "c": cid, "p": project, "ec": company, "ar": northwind})).scalar()
        ts = (await conn.execute(text(
            """insert into mytrakin.timesheets (tenant_id, consultant_id, week_start, status, note, submitted_at)
               values (:t, :c, :w, 'submitted', 'Client approval flow test', now()) returning id"""),
            {"t": esg, "c": cid, "w": week})).scalar()
        await conn.execute(text(
            """insert into mytrakin.timesheet_entries (tenant_id, timesheet_id, placement_id, work_date, hours)
               select :t, :ts, :p, :w + n, 2 from generate_series(0, 4) n"""), {"t": esg, "ts": ts, "p": pid, "w": week})
        return str(ts), str(pid)


async def _add_link(client, ts_id: str) -> str:
    """A stored link with a known token (the flow itself hashes its real tokens)."""
    async with get_engine().begin() as conn:
        await conn.execute(text(
            """insert into mytrakin.ts_approval_links (tenant_id, timesheet_id, token_hash)
               values ((select id from mytrakin.tenants where name like 'Executive Software Guild%' limit 1),
                       :ts, :h)"""), {"ts": ts_id, "h": sha256_hex(TOKEN)})
    return TOKEN


async def test_placed_by_approval_flows_to_the_end_client_and_auto_invoices(client, auth):
    finance = auth("finance")
    company = await _linkable_client()
    ts_id, placement_id = await _submitted_week(client, company, THIS_WEEK)

    # 1. The placing company approves: the week stays 'submitted', now placed-by approved.
    approved = await client.post(f"/timesheets/{ts_id}/approve", headers=finance)
    assert approved.status_code == 200, approved.text
    row = approved.json()
    assert row["status"] == "submitted" and row["placed_by_approved"] and not row["end_client_approved"], row

    # 2. The end client's person opens the link and sees the week (no account needed).
    token = await _add_link(client, ts_id)
    view = await client.get(f"/public/ts-approvals/{token}")
    assert view.status_code == 200, view.text
    body = view.json()
    assert body["consultant"] == "Link Client Person" and Decimal(str(body["total_hours"])) == 10, body

    # 3. Approving through the link finalises the week...
    decided = await client.post(f"/public/ts-approvals/{token}/approve", json={})
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved", decided

    # 4. ...and invoices for the week are generated automatically (10h x $60).
    await asyncio.sleep(3.5)
    invoices = (await client.get("/invoices", params={"direction": "ar"}, headers=finance)).json()
    ar = [i for i in invoices if i.get("placement_id") == placement_id and str(i["period_start"] or "") == str(THIS_WEEK)]
    assert ar, invoices
    assert Decimal(str(ar[0]["amount"])) == Decimal("600.00"), ar


async def test_the_end_client_can_also_return_the_week_with_a_note(client, auth):
    finance = auth("finance")
    company = await _linkable_client()
    ts_id, _pid = await _submitted_week(client, company, NEXT_WEEK)
    # placed-by approval first
    assert (await client.post(f"/timesheets/{ts_id}/approve", headers=finance)).status_code == 200
    token = await _add_link(client, ts_id)

    # Without a note the return is refused...
    short = await client.post(f"/public/ts-approvals/{token}/return", json={"note": "fix"})
    assert short.status_code == 400, short.text

    # ...and with one it goes back to the consultant, placed-by approval cleared.
    returned = await client.post(f"/public/ts-approvals/{token}/return",
                                 json={"note": "Friday hours need client sign-off"})
    assert returned.status_code == 200 and returned.json()["status"] == "rejected", returned.text
    async with get_engine().begin() as conn:
        row = (await conn.execute(text(
            "select status, reject_reason, placed_by_approved, end_client_approved from mytrakin.timesheets where id = :t"),
            {"t": ts_id})).mappings().first()
    assert row["status"] == "rejected" and "Friday hours" in row["reject_reason"], row
    assert not row["placed_by_approved"] and not row["end_client_approved"], row


async def test_the_client_sees_the_week_in_its_own_timesheets_page(client, auth):
    """A's (the end client's) Timesheets page: the queue card shows weeks waiting on them,
    and they can act on one from their own workspace — approve generates invoices."""
    admin = auth("finance")
    company_tenant, company = await _linkable_client()
    ts_id, _pid = await _submitted_week(client, company, THIS_WEEK + timedelta(days=7))
    assert (await client.post(f"/timesheets/{ts_id}/approve", headers=admin)).status_code == 200

    client_admin = {**auth("admin"), "X-Tenant-Id": company_tenant}
    queue = (await client.get("/timesheets/client-queue", headers=client_admin)).json()
    mine = [q for q in queue if q["timesheet_id"] == ts_id]
    assert mine and mine[0]["consultant"] == "Link Client Person", queue

    decided = await client.post(f"/timesheets/{ts_id}/client-decision", headers=client_admin,
                                json={"decision": "approve"})
    assert decided.status_code == 200 and decided.json()["status"] == "approved", decided.text

    # The completed week leaves the queue and shows in the client's own History tab,
    # even though the timesheet belongs to the placing workspace.
    history = (await client.get("/timesheets/history", headers=client_admin)).json()
    mine = [h for h in history if h["id"] == ts_id]
    assert mine and all(h["status"] == "approved" for h in mine), mine

    # and the placements block others' workspaces from the queue / decisions
    outsider = await client.get("/timesheets/client-queue", headers=auth("finance"))
    assert all(q["timesheet_id"] != ts_id for q in (outsider.json() or []))
