"""Timesheets: one per consultant per week, one line per project.

Consultants enter and submit; the admin (or an approver) validates against the
automatic checks and approves or rejects with a reason. Approved weeks are locked
and feed invoicing."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator

from ..config import get_settings
from ..deps import TenantDb, open_system, tenant_db
from ..errors import ApiError, bad_request, not_found
from ..services import workflow
from ..services.email import render, send_email
from ..services.invoicing import generate_invoices
from ..services.timesheet_checks import Entry, PlacementInfo, run_checks, summarize
from ..utils import sha256_hex, week_start

router = APIRouter(prefix="/timesheets", tags=["timesheets"])

APPROVER_ROLES = ("approver", "account_manager", "hr", "finance")


class Row(BaseModel):
    placement_id: UUID | None = None          # None = internal / non-billable
    hours: list[Decimal] = Field(min_length=7, max_length=7)

    @field_validator("hours")
    @classmethod
    def _range(cls, v: list[Decimal]) -> list[Decimal]:
        if any(h < 0 or h > 24 for h in v):
            raise ValueError("Each day must be between 0 and 24 hours")
        return v


class WeekIn(BaseModel):
    week_start: date
    rows: list[Row] = Field(max_length=20)
    note: str | None = Field(None, max_length=1000)


class Decision(BaseModel):
    reason: str | None = Field(None, max_length=500)


class WeekendNote(BaseModel):
    note: str | None = Field(None, max_length=500)


def _sunday(day: date) -> date:
    if day.weekday() != 6:
        raise bad_request("week_start must be a Sunday")
    return day


async def _weekend_hours(db: TenantDb, timesheet_id) -> Decimal:
    """Hours logged on Saturday/Sunday (dow 0 = Sunday, 6 = Saturday)."""
    return Decimal(await db.val(
        "select coalesce(sum(hours), 0) from timesheet_entries"
        " where timesheet_id = :id and extract(dow from work_date) in (0, 6)",
        {"id": timesheet_id}))


async def _consultant_email(db: TenantDb, consultant_id) -> str | None:
    """The consultant's login e-mail, or the address on their consultant record."""
    row = await db.one(
        """select coalesce(p.email, c.email) as email from consultants c
             left join profiles p on p.id = c.user_id where c.id = :c""", {"c": consultant_id})
    return row["email"] if row and row["email"] else None


async def _user_email(db: TenantDb, user_id) -> str | None:
    row = await db.one("select email from profiles where id = :u", {"u": user_id})
    return row["email"] if row else None


async def _end_clients(db: TenantDb, tenant_id, timesheet_id) -> set:
    """End-client companies on this timesheet's placements whose representative is a
    member of the placing workspace (its contact invited with that company)."""
    chain = {r["cid"] for r in await db.all(
        """select distinct p.end_client_company_id as cid
             from timesheet_entries e join placements p on p.id = e.placement_id
            where e.timesheet_id = :id and p.end_client_company_id is not null""", {"id": timesheet_id})}
    reps = {r["cid"] for r in await db.all(
        """select distinct m.company_id as cid from mytrakin.memberships m
            where m.tenant_id = :t and m.status = 'active' and m.company_id is not null""", {"t": tenant_id})}
    return chain & reps


async def _auto_invoice(week_start: date, tenant_id, user_id) -> None:
    """After a final approval the week's invoices are generated automatically — AR for
    the agreed bill rate to the customer, AP for the agreed pay rate to the consultant's
    payee (RULE-01: only our own links, never a counterparty's money).

    Runs on its own system connection (any approver role can trigger it, even the end
    client's representative, who has no invoice rights in this workspace). The approval
    commits when the request ends, so the small delay makes sure the week is approved
    in the database before the generation reads it. Failures are logged, never surfaced
    to the approving user, and finance can always generate the same invoices by hand."""
    log = logging.getLogger("mytrakin.timesheets")
    await asyncio.sleep(2)
    try:
        async for db in open_system(tenant_id):
            created, blocked = await generate_invoices(
                db, tenant_id=tenant_id, user_id=user_id,
                period_start=week_start, period_end=week_start + timedelta(days=6))
            if created:
                log.info("auto-invoiced week of %s for tenant %s: %s", week_start, tenant_id,
                         [(i["direction"], i["number"], str(i["amount"])) for i in created])
            if blocked:
                log.warning("auto-invoicing skipped some placements for week of %s (tenant %s): %s",
                            week_start, tenant_id, blocked)
    except Exception:       # noqa: BLE001 — never fail the approval because invoicing hiccuped
        log.exception("auto-invoicing failed for tenant %s week of %s", tenant_id, week_start)


async def _end_client_recipients(db: TenantDb, tenant_id, chain: set) -> dict:
    """Who can be asked to approve for each end-client company: people of the client's
    own myTrakIn workspace, or representatives invited into this workspace. Returns
    {company_id: [emails]} for companies with at least one reachable person."""
    out: dict = {}
    if not chain:
        return out
    rep_emails: dict = {}
    for r in await db.all(
        """select m.company_id as cid, p.email from mytrakin.memberships m
             join profiles p on p.id = m.user_id
            where m.tenant_id = :t and m.status = 'active' and m.user_id is not null
              and m.company_id is not null""", {"t": tenant_id}):
        rep_emails.setdefault(r["cid"], []).append(r["email"])
    ws_emails: dict = {}
    # The end client's own workspace lives in a different tenant — invisible to this
    # session under RLS — so discovery goes through the SECURITY DEFINER helper.
    # asyncpg encodes a Python list for uuid[] (a string literal fails).
    for r in await db.all(
        """select * from mytrakin.ts_client_recipients(cast(:ids as uuid[]))""",
            {"ids": sorted(str(c) for c in chain)}):
        ws_emails.setdefault(r["company_id"], []).append(r["email"])
    for cid in chain:
        seen: set = set()
        emails: list = []
        for e in (*rep_emails.get(cid, ()), *ws_emails.get(cid, ())):
            if e and e not in seen:
                seen.add(e)
                emails.append(e)
        if emails:
            out[cid] = emails
    return out


async def _send_client_approval(db: TenantDb, ts: dict, recipients: dict, timesheet_id) -> None:
    """Create one approval link per end-client company and e-mail its people.
    The link (like an e-signature link) shows the week and lets them approve it
    or return it with a note — no account inside this workspace needed."""
    settings = get_settings()
    placing = await db.val("select name from mytrakin.tenants where id = :t", {"t": ts["tenant_id"]}) or "The placing company"
    total = Decimal(await db.val("select coalesce(sum(hours), 0) from timesheet_entries where timesheet_id = :id",
                                 {"id": timesheet_id}))
    for cid, emails in recipients.items():
        token = secrets.token_urlsafe(32)
        await db.run(
            """insert into mytrakin.ts_approval_links (tenant_id, timesheet_id, company_id, token_hash, created_by)
               values (:t, :ts, :c, :h, :u)""",
            {"t": ts["tenant_id"], "ts": timesheet_id, "c": cid, "h": sha256_hex(token), "u": db.ctx.user_id})
        await send_email(db, to=emails, subject=f"Timesheet to approve — {ts['consultant']}, week of {ts['week_start']}",
                         kind="timesheet", tenant_id=ts["tenant_id"], ref_type="timesheet", ref_id=timesheet_id,
                         html_body=render(f"{placing} approved a timesheet — your approval is next",
                                          [f"{placing} approved {ts['consultant']}'s timesheet for the week of "
                                           f"{ts['week_start']} ({total:g} hours across their projects).",
                                           "Open the link to review the hours and approve — or return the week "
                                           "with a note. Once you approve, invoices for the week are generated "
                                           "automatically."],
                                          button=("Review & approve", f"{settings.web_origin.rstrip('/')}/approve/timesheet/{token}")))


async def _checks(db: TenantDb, consultant_id: UUID | None = None, week_start: date | None = None,
                  timesheet_id: UUID | None = None) -> tuple[list, dict]:
    """Run automatic checks on a timesheet's entries.

    Look up entries either by a single timesheet_id (review page) or across all
    timesheets for a consultant/week (week overview, where one consultant may have
    multiple timesheets — one per placement — after the per-placement split).
    """
    if timesheet_id is not None:
        entries = await db.all("select placement_id, work_date, hours from timesheet_entries where timesheet_id = :id", {"id": timesheet_id})
        ts = await db.one("select consultant_id, week_start, status from timesheets where id = :id", {"id": timesheet_id})
        consultant_id = ts["consultant_id"]
        week_start = ts["week_start"]
        status = ts["status"]
    else:
        entries = await db.all(
            """select placement_id, work_date, hours from timesheet_entries e
                 join timesheets t on t.id = e.timesheet_id
                where t.consultant_id = :c and t.week_start = :ws""",
            {"c": consultant_id, "ws": week_start})
        ts_row = await db.one(
            """select case when bool_or(status = 'submitted') then 'submitted'
                          when bool_or(status = 'rejected') then 'rejected'
                          when bool_or(status = 'draft') then 'draft'
                          when bool_or(status = 'approved') then 'approved'
                          else 'not_submitted' end as status
                 from timesheets where consultant_id = :c and week_start = :ws""",
            {"c": consultant_id, "ws": week_start})
        status = ts_row["status"] if ts_row and ts_row["status"] else "draft"
    placements = await db.all(
        """select p.id, p.hours_per_week, p.start_date, p.end_date, p.bill_rate, s.code as sow_code,
                  (s.value_cap - b.invoiced) as sow_remaining
             from placements p left join sows s on s.id = p.ar_sow_id left join sow_burn b on b.sow_id = s.id
            where p.consultant_id = :c and p.start_date <= :we and coalesce(p.end_date, :ws) >= :ws""",
        {"c": consultant_id, "ws": week_start, "we": week_start + timedelta(days=6)})
    checks = run_checks(
        status=status,
        week_start=week_start,
        entries=[Entry(str(e["placement_id"]) if e["placement_id"] else None, e["work_date"], Decimal(e["hours"])) for e in entries],
        placements={str(p["id"]): PlacementInfo(str(p["id"]), Decimal(p["hours_per_week"]), p["start_date"], p["end_date"],
                                                p["bill_rate"], p["sow_code"], p["sow_remaining"]) for p in placements},
        engagement=None,
        show_money=False,
    )
    return [c.as_dict() for c in checks], summarize(checks)


async def _contract_gate(db: TenantDb, timesheet_id) -> None:
    """Resource contract → acceptance → timesheet (WF-05). For each project on the week: the resource needs a contract
    (vendor / 1099 work order, or a W-2 offer letter) and, when acceptance is required, that contract and the client
    SOW must be accepted (signed or recorded). Each check follows its tenant workflow switch."""
    rules = await workflow.rules(db)
    if not (rules["requireContract"] or rules["requireAcceptance"]):
        return
    rows = await db.all(
        """select distinct pr.name as project, et.pay_model, aps.code as ap_sow, aps.status as ap_status,
                  ars.code as ar_sow, ars.status as ar_status,
                  (select o.status from agreements o where o.consultant_id = p.consultant_id and o.kind = 'offer_letter'
                    order by o.status = 'active' desc, o.created_at desc limit 1) as offer_status,
                  mytrakin.consultant_agreement_in_force(p.consultant_id, array['offer_letter'], current_date)
                    as offer_in_force
             from timesheet_entries e join placements p on p.id = e.placement_id join projects pr on pr.id = p.project_id
             join consultants c on c.id = p.consultant_id join engagement_types et on et.code = c.engagement
             left join sows aps on aps.id = p.ap_sow_id left join sows ars on ars.id = p.ar_sow_id
            where e.timesheet_id = :id""", {"id": timesheet_id})
    for r in rows:
        payroll = r["pay_model"] == "payroll"
        contract_status = r["offer_status"] if payroll else r["ap_status"]
        what = "offer letter" if payroll else "vendor / contractor work order"
        # A W-2 resource contract is the offer letter (it counts from any workspace the
        # person works in). A vendor / 1099 contractor's resource contract is the AP work
        # order on the placement — an offer letter for the same person elsewhere must not
        # stand in for a missing work order.
        contract_ok = r["offer_in_force"] if payroll else contract_status is not None
        if rules["requireContract"] and not contract_ok:
            raise workflow.blocked("contract_required", f"{r['project']}: no {what} for this resource yet — add it before "
                                                        "timesheets (or turn off 'Require contract' in Settings → Workflow)")
        if rules["requireAcceptance"]:
            if contract_status is not None and contract_status != "active" \
                    and not (payroll and r["offer_in_force"]):
                raise workflow.blocked("acceptance_required", f"{r['project']}: the {what} isn't accepted yet")
            if r["ar_sow"] and r["ar_status"] != "active":
                raise workflow.blocked("acceptance_required", f"{r['project']}: client SOW {r['ar_sow']} isn't accepted yet")


@router.get("")
async def week_overview(db: TenantDb = Depends(tenant_db), week: date | None = None):
    """Every consultant with work that week: hours per day, status and the result of the checks."""
    if not db.ctx.internal and db.ctx.role != "vendor_admin":
        raise ApiError(403, "forbidden", "Consultants see their own timesheets under My timesheet")
    ws = _sunday(week) if week else week_start(date.today())
    rows = await db.all(
        """select c.id as consultant_id, c.full_name, c.engagement, emp.name as employer,
                  ts_agg.id, ts_agg.status, ts_agg.placed_by_approved,
                  ts_agg.submitted_at, ts_agg.reject_reason, ts_agg.note,
                  (select string_agg(distinct pr.name, ', ') from placements p join projects pr on pr.id = p.project_id
                    where p.consultant_id = c.id and p.start_date <= cast(:ws as date) + 6
                      and coalesce(p.end_date, cast(:ws as date)) >= :ws) as projects,
                  coalesce(ts_agg.days, '{0,0,0,0,0,0,0}') as days
               from consultants c
               left join companies emp on emp.id = c.employer_company_id
               left join lateral (
                   -- Postgres has no min(uuid): pick the week's timesheet that most needs
                   -- attention (submitted, then returned, then the oldest draft) so a click
                   -- opens the one awaiting approval when a consultant has several projects.
                   select (array_agg(t.id order by (t.status = 'submitted') desc,
                                                 (t.status = 'rejected') desc, t.created_at))[1] as id,
                          case when bool_or(t.status = 'submitted') then 'submitted'
                               when bool_or(t.status = 'rejected') then 'rejected'
                               when bool_or(t.status = 'draft') then 'draft'
                               when bool_or(t.status = 'approved') then 'approved'
                               else 'not_submitted' end as status,
                          bool_or(t.placed_by_approved) as placed_by_approved,
                          max(t.submitted_at) as submitted_at,
                          max(t.reject_reason) as reject_reason,
                          max(t.note) as note,
                          (select array_agg(coalesce(dh.sum_hours, 0) order by dh.dn)
                           from (
                               select g.dn, coalesce(sum(e.hours), 0) as sum_hours
                               from generate_series(0, 6) g(dn)
                               left join timesheet_entries e on (e.work_date - cast(:ws as date)) = g.dn
                                  and e.timesheet_id in (select id from timesheets where consultant_id = c.id and week_start = :ws)
                               group by g.dn
                           ) dh(dn, sum_hours)
                          ) as days
                   from timesheets t
                   where t.consultant_id = c.id and t.week_start = :ws
               ) ts_agg on true
              where c.status = 'active'
                -- Approved weeks are done: they move to History and no longer need an approver.
                and (ts_agg.id is null or ts_agg.status <> 'approved')
                and (ts_agg.id is not null or exists (select 1 from placements p where p.consultant_id = c.id
                                                        and p.start_date <= cast(:ws as date) + 6 and coalesce(p.end_date, cast(:ws as date)) >= :ws))
              order by c.full_name""",
        {"ws": ws})
    for r in rows:
        r["total"] = sum((Decimal(h) for h in r["days"]), Decimal(0))
        if r["id"]:
            _, r["checks"] = await _checks(db, consultant_id=r["consultant_id"], week_start=ws)
        else:
            r["checks"] = None
    return {"week_start": ws, "rows": rows}


@router.get("/history")
async def history(db: TenantDb = Depends(tenant_db), consultant_id: UUID | None = None,
                  since: date | None = Query(None, alias="from"), until: date | None = Query(None, alias="to")):
    """All weeks, one line per consultant, week and project.

    Internal staff and vendor admins see everything. A client_user (end client
    representative) only sees weeks where their company is the end client on at
    least one placement in the timesheet.

    A company's own workspace never owns the weeks it approves — they belong to
    the placing workspace, hidden by tenant isolation — so the completed weeks
    where it was the end client are added through ts_client_history(), the
    read-only counterpart of the pending queue.
    """
    if not db.ctx.internal and db.ctx.role not in ("vendor_admin", "client_user"):
        raise ApiError(403, "forbidden", "Use My timesheet for your own history")

    company_id = db.ctx.company_id
    # For client_user, resolve the company if it isn't already on the request
    # context (e.g. when only a company membership exists without a workspace row).
    if db.ctx.role == "client_user" and company_id is None:
        company_id = await db.val(
            "select company_id from mytrakin.memberships where id = :m",
            {"m": db.ctx.membership_id})
        if company_id is None and db.ctx.user_id is not None:
            company_id = await db.val(
                "select company_id from mytrakin.company_members"
                " where user_id = :uid and status = 'active' order by created_at desc limit 1",
                {"uid": db.ctx.user_id})
    # Make sure ctx_company() reflects the resolved company so RLS policies that
    # read ctx_company() (e.g. timesheets_client_read) work correctly in this session.
    if db.ctx.role == "client_user" and company_id is not None:
        await db.run("select set_config('app.company_id', :cid, true)",
                     {"cid": str(company_id)})

    rows = await db.all(
        """select t.id, t.week_start, t.status, t.placed_by_approved, t.end_client_approved,
                  c.full_name, c.id as consultant_id, coalesce(pr.name, 'Internal') as project,
                  sum(e.hours) as hours, t.decided_at
              from timesheets t join consultants c on c.id = t.consultant_id
              join timesheet_entries e on e.timesheet_id = t.id
              left join placements p on p.id = e.placement_id left join projects pr on pr.id = p.project_id
             where (cast(:c as uuid) is null or t.consultant_id = :c)
               and (cast(:f as date) is null or t.week_start >= :f) and (cast(:u as date) is null or t.week_start <= :u)
               and (:role <> 'client_user' or exists (
                     select 1 from timesheet_entries e2
                     join placements p2 on p2.id = e2.placement_id
                    where e2.timesheet_id = t.id and p2.end_client_company_id = :co))
             group by t.id, c.id, pr.name, t.placed_by_approved, t.end_client_approved
             order by t.week_start desc, c.full_name, project
             limit 2000""",
        {"c": consultant_id, "f": since, "u": until, "role": db.ctx.role, "co": company_id})

    seen = {(str(r["id"]), r["project"]) for r in rows}
    for r in await db.all(
            """select timesheet_id as id, week_start, status, placed_by_approved, end_client_approved,
                      consultant as full_name, consultant_id, project, hours, decided_at
                 from mytrakin.ts_client_history()
                where (cast(:c as uuid) is null or consultant_id = :c)
                  and (cast(:f as date) is null or week_start >= :f)
                  and (cast(:u as date) is null or week_start <= :u)""",
            {"c": consultant_id, "f": since, "u": until}):
        key = (str(r["id"]), r["project"])
        if key not in seen:
            seen.add(key)
            rows.append(r)
    rows.sort(key=lambda r: (r["full_name"], r["project"]))
    rows.sort(key=lambda r: r["week_start"], reverse=True)
    return rows


# ----------------------------------------------------------------------------- consultant
@router.get("/mine")
async def my_week(db: TenantDb = Depends(tenant_db), week: date | None = None):
    if db.ctx.role != "consultant":
        raise ApiError(403, "forbidden", "Only consultants have a personal timesheet")
    ws = _sunday(week) if week else week_start(date.today())
    projects = await db.all(
        """select p.id as placement_id, pr.name as project, p.role_title, p.hours_per_week,
                  mytrakin.company_public_name(p.end_client_company_id) as end_client
             from placements p join projects pr on pr.id = p.project_id
            where p.consultant_id = :c and p.status in ('active', 'ending', 'onboarding')
              and p.start_date <= cast(:ws as date) + 6 and coalesce(p.end_date, cast(:ws as date)) >= :ws
            order by pr.name""",
        {"c": db.ctx.consultant_id, "ws": ws})
    # One timesheet per placement after the per-placement split. Return per-timesheet
    # details so the frontend can show independent submit buttons per project.
    tss = await db.all("select id, status, note, placed_by_approved, end_client_approved, reject_reason, weekend_requested_at, weekend_review_note, weekend_confirmed from timesheets where consultant_id = :c and week_start = :ws",
                       {"c": db.ctx.consultant_id, "ws": ws})
    ts_by_placement: dict[str, dict] = {}
    for ts in tss:
        for e in await db.all("select placement_id from timesheet_entries where timesheet_id = :id", {"id": ts["id"]}):
            pid = str(e["placement_id"]) if e["placement_id"] else None
            ts_by_placement[pid] = ts
    grid: dict[str | None, list[Decimal]] = defaultdict(lambda: [Decimal(0)] * 7)
    for ts in tss:
        for e in await db.all("select placement_id, work_date, hours from timesheet_entries where timesheet_id = :id", {"id": ts["id"]}):
            pid = str(e["placement_id"]) if e["placement_id"] else None
            grid[pid][(e["work_date"] - ws).days] += Decimal(e["hours"])
    rows = []
    for p in projects:
        pid = str(p["placement_id"])
        ts = ts_by_placement.get(pid)
        rows.append({"placement_id": p["placement_id"], "project": p["project"],
                     "hours": grid.get(pid, [Decimal(0)] * 7),
                     "timesheet_id": ts["id"] if ts else None,
                     "ts_status": ts["status"] if ts else "draft",
                     "ts_placed_by_approved": bool(ts["placed_by_approved"]) if ts else False,
                     "ts_end_client_approved": bool(ts["end_client_approved"]) if ts else False,
                     "ts_end_client": p["end_client"]})
    if None in grid:
        ts = ts_by_placement.get(None)
        rows.append({"placement_id": None, "project": "Internal / non-billable", "hours": grid[None],
                     "timesheet_id": ts["id"] if ts else None,
                     "ts_status": ts["status"] if ts else "draft",
                     "ts_placed_by_approved": bool(ts["placed_by_approved"]) if ts else False,
                     "ts_end_client_approved": bool(ts["end_client_approved"]) if ts else False,
                     "ts_end_client": None})
    # TS-10: approved time off shown per day (read-only, never saved as hours or billed).
    off = await db.all(
        """select starts_on, ends_on, kind from time_off where consultant_id = :c and status in ('approved', 'holiday')
            and starts_on <= cast(:ws as date) + 6 and ends_on >= :ws""", {"c": db.ctx.consultant_id, "ws": ws})
    time_off = [next((o["kind"] for o in off if o["starts_on"] <= ws + timedelta(days=i) <= o["ends_on"]), None) for i in range(7)]
    # Aggregate approval state across all timesheets for this week.
    any_submitted = any(t["status"] == "submitted" for t in tss)
    any_approved = any(t["status"] == "approved" for t in tss)
    status = "approved" if any_approved else ("submitted" if any_submitted else ("draft" if tss else "not_submitted"))
    placed_by_approved = any(t["placed_by_approved"] for t in tss)
    end_client_approved = any(t["end_client_approved"] for t in tss)
    reject_reason = next((t["reject_reason"] for t in tss if t["reject_reason"]), None)
    note = next((t["note"] for t in tss if t["note"]), "")
    # Company names for the approval-status panel: the placing workspace and the
    # end client(s) on the weeks' placements (public names � cross-tenant safe).
    placed_by = None
    if db.ctx.tenant_id:
        placed_by = await db.val("select name from mytrakin.tenants where id = :t", {"t": db.ctx.tenant_id})
    end_clients = [r["name"] for r in await db.all(
        """select distinct mytrakin.company_public_name(p.end_client_company_id) as name
             from placements p
            where p.consultant_id = :c and p.end_client_company_id is not null
              and p.start_date <= cast(:ws as date) + 6 and coalesce(p.end_date, cast(:ws as date)) >= :ws""",
        {"c": db.ctx.consultant_id, "ws": ws}) if r["name"]]
    # Weekend state from the most recent timesheet.
    weekend_ts = max(tss, key=lambda t: t["id"]) if tss else None
    return {"week_start": ws, "status": status, "reject_reason": reject_reason,
            "note": note,
            "placed_by_approved": placed_by_approved,
            "end_client_approved": end_client_approved,
            "placed_by_name": placed_by, "end_client_names": end_clients,
            "weekend_requested": bool(weekend_ts and weekend_ts["weekend_requested_at"]),
            "weekend_review_note": weekend_ts["weekend_review_note"] if weekend_ts else None,
            "weekend_confirmed": weekend_ts["weekend_confirmed"] if weekend_ts else None,
            "rows": rows, "projects": projects, "time_off": time_off}

@router.put("/mine")
async def save_my_week(body: WeekIn, db: TenantDb = Depends(tenant_db)):
    if db.ctx.role != "consultant":
        raise ApiError(403, "forbidden", "Only consultants have a personal timesheet")
    ws = _sunday(body.week_start)
    if ws > week_start(date.today()) + timedelta(days=7):
        raise bad_request("You can't enter time more than a week ahead")
    allowed = {str(r["id"]) for r in await db.all("select id from placements where consultant_id = :c", {"c": db.ctx.consultant_id})}
    for row in body.rows:
        if row.placement_id and str(row.placement_id) not in allowed:
            raise bad_request("One of the projects isn't assigned to you")
    # Save one timesheet per placement, upserting in place: submitting one project
    # must not stop the others being entered, and saving one project must not wipe
    # another project's draft. Only a submitted/approved project itself is locked.
    # Rejected projects can be edited and resubmitted until they are approved.
    for row in body.rows:
        existing = await db.one(
            """select t.id, t.status from timesheets t
                where t.consultant_id = :c and t.week_start = :ws
                  and exists (select 1 from timesheet_entries e
                               where e.timesheet_id = t.id
                                 and e.placement_id is not distinct from :p)
                order by t.created_at desc limit 1""",
            {"c": db.ctx.consultant_id, "ws": ws, "p": row.placement_id})
        if existing and existing["status"] in ("submitted", "approved"):
            continue
        # Remove only this project's days; a legacy timesheet can also hold another
        # placement's days, which must survive.
        if existing:
            await db.run(
                """delete from timesheet_entries
                    where timesheet_id = :id and placement_id is not distinct from :p""",
                {"id": existing["id"], "p": row.placement_id})
        entry_rows = [{"t": db.ctx.tenant_id, "ts": None, "p": row.placement_id,
                       "d": ws + timedelta(days=i), "h": h}
                      for i, h in enumerate(row.hours) if h > 0]
        if not entry_rows:
            if existing:
                left = await db.val("select count(*) from timesheet_entries where timesheet_id = :id",
                                    {"id": existing["id"]})
                if not left:
                    await db.run("delete from timesheets where id = :id", {"id": existing["id"]})
            continue
        if existing:
            left = await db.val("select count(*) from timesheet_entries where timesheet_id = :id",
                                {"id": existing["id"]})
            if not left:
                tid = existing["id"]
                await db.run("update timesheets set note = :n, updated_at = now() where id = :id",
                             {"n": body.note, "id": tid})
            else:
                # The old week-wide timesheet keeps its other placement; this project
                # gets its own timesheet now.
                existing = None
        if not existing:
            ts = await db.one(
                "insert into timesheets (tenant_id, consultant_id, week_start, note) "
                "values (:t, :c, :ws, :n) returning id",
                {"t": db.ctx.tenant_id, "c": db.ctx.consultant_id, "ws": ws, "n": body.note})
            tid = ts["id"]
        for er in entry_rows:
            er["ts"] = tid
        await db.run(
            """insert into timesheet_entries (tenant_id, timesheet_id, placement_id, work_date, hours)
               values (:t, :ts, :p, :d, :h)""", entry_rows)
    return await my_week(db, ws)


@router.post("/mine/submit")
async def submit_my_week(body: Decision, db: TenantDb = Depends(tenant_db), week: date = Query(...)):
    if db.ctx.role != "consultant":
        raise ApiError(403, "forbidden", "Only consultants submit timesheets")
    ws = _sunday(week)
    tss = await db.all("select id, note from timesheets where consultant_id = :c and week_start = :ws",
                       {"c": db.ctx.consultant_id, "ws": ws})
    if not tss:
        raise bad_request("Enter your hours first")
    for ts in tss:
        if not ts["note"] or not ts["note"].strip():
            raise bad_request("Please enter a note before submitting the timesheet.")
        total = await db.val("select coalesce(sum(hours), 0) from timesheet_entries where timesheet_id = :id",
                             {"id": ts["id"]})
        if total <= 0:
            raise bad_request("Enter your hours first")
    # Submit each timesheet individually � each project is routed to its own
    # placed-by company and end client for independent approval.
    for ts in tss:
        await _contract_gate(db, ts["id"])
        await db.run(
            """update timesheets set status = 'submitted', submitted_at = now(), reject_reason = null,
                 placed_by_approved = false, end_client_approved = false, weekend_confirmed = false,
                 weekend_requested_by = null, weekend_requested_at = null, weekend_review_note = null
                 where id = :id""", {"id": ts["id"]})
    return {"id": tss[0]["id"], "status": "submitted"}


@router.post("/{timesheet_id}/submit")
async def submit_my_timesheet(timesheet_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Submit a single timesheet (one project) for approval."""
    if db.ctx.role != "consultant":
        raise ApiError(403, "forbidden", "Only consultants submit timesheets")
    ts = await db.one("select id, status, note from timesheets where id = :id and consultant_id = :c",
                      {"id": timesheet_id, "c": db.ctx.consultant_id})
    if ts is None:
        raise not_found("Timesheet")
    if ts["status"] not in ("draft", "rejected"):
        raise ApiError(409, "not_submittable", "Only draft or rejected timesheets can be submitted")
    if not ts["note"] or not ts["note"].strip():
        raise bad_request("Please enter a note before submitting the timesheet.")
    total = await db.val("select coalesce(sum(hours), 0) from timesheet_entries where timesheet_id = :id",
                         {"id": timesheet_id})
    if total <= 0:
        raise bad_request("Enter your hours first")
    await _contract_gate(db, timesheet_id)
    await db.run(
        """update timesheets set status = 'submitted', submitted_at = now(), reject_reason = null,
             placed_by_approved = false, end_client_approved = false, weekend_confirmed = false,
             weekend_requested_by = null, weekend_requested_at = null, weekend_review_note = null
             where id = :id""", {"id": timesheet_id})
    return {"id": timesheet_id, "status": "submitted"}


# ----------------------------------------------------------------------------- review
def _client_approver(db: TenantDb) -> None:
    """Internal staff, or a client_user representative acting for their company."""
    if not (db.ctx.allows(*APPROVER_ROLES) or db.ctx.role == "client_user"):
        raise ApiError(403, "forbidden", "This page is for timesheet approvers")


@router.get("/client-queue")
async def client_queue(db: TenantDb = Depends(tenant_db)):
    """Weeks whose placed-by approval is in and are waiting on our end-client approval.
    Visible from the end client's own workspace (and to its representatives)."""
    _client_approver(db)
    return await db.all("select * from mytrakin.ts_client_queue()")


class ClientDecision(BaseModel):
    decision: str = Field(pattern="^(approve|return)$")
    note: str | None = Field(None, max_length=500)


@router.post("/{timesheet_id}/client-decision")
async def client_decision(timesheet_id: UUID, body: ClientDecision, db: TenantDb = Depends(tenant_db)):
    """The end client's in-app decision on a week waiting for their approval."""
    _client_approver(db)
    res = await db.val("select mytrakin.ts_client_decide_ts(:ts, :d, :n)",
                       {"ts": timesheet_id, "d": body.decision, "n": body.note})
    # asyncpg (and SQLAlchemy above it) may hand back dict|str for a json result
    # depending on the codec settings — accept both.
    res = res if isinstance(res, dict) else json.loads(res)
    err = res.get("error")
    if err == "note_required":
        raise bad_request("Add a short note so the consultant knows what to fix.")
    if err == "not_ours":
        raise ApiError(403, "forbidden", "Your company is not the end client on this timesheet")
    if err == "not_ready":
        raise ApiError(409, "not_ready", "This week isn't waiting for the end client's approval any more")
    if err:
        raise bad_request("That decision isn't recognised")
    if res.get("status") == "approved":
        asyncio.create_task(_auto_invoice(date.fromisoformat(res["week_start"]), res["tenant_id"], db.ctx.user_id))
    await _client_decision_emails(db, res, note=body.note)
    return res


@router.post("/{timesheet_id}/client-link")
async def client_link(timesheet_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Create a fresh approval link the end client's person can act on right away."""
    _client_approver(db)
    token = secrets.token_urlsafe(32)
    res = await db.val("select mytrakin.ts_client_link(:ts, :h, :u)",
                       {"ts": timesheet_id, "h": sha256_hex(token), "u": db.ctx.user_id})
    res = res if isinstance(res, dict) else json.loads(res)
    if res.get("error") == "not_ours":
        raise ApiError(403, "forbidden", "Your company is not the end client on this timesheet")
    if res.get("error"):
        raise ApiError(409, "not_ready", "This week isn't waiting for the end client's approval any more")
    return {"token": token, "timesheet_id": timesheet_id}


async def _client_decision_emails(db: TenantDb, res: dict, note: str | None = None) -> None:
    """Tell the placing company (and on a return, the consultant) what the end client decided."""
    settings = get_settings()
    week = res.get("week_start")
    who = res.get("company_name") or "The end client"
    if res.get("status") == "approved" and res.get("creator_email"):
        await send_email(db, to=res["creator_email"], subject=f"Timesheet approved by the client — week of {week}",
                         kind="timesheet", tenant_id=res.get("tenant_id"), ref_type="timesheet",
                         ref_id=res.get("timesheet_id"),
                         html_body=render("Timesheet approved by the client",
                                          [f"{who} approved {res.get('consultant')}'s timesheet for the week of {week}.",
                                           "Invoices for the week will be generated automatically."],
                                          button=("Open timesheets", f"{settings.web_origin.rstrip('/')}/timesheets")))
    if res.get("status") == "rejected":
        body = note or ""
        if res.get("creator_email"):
            await send_email(db, to=res["creator_email"], subject=f"Timesheet returned by the client — week of {week}",
                             kind="timesheet", tenant_id=res.get("tenant_id"), ref_type="timesheet",
                             ref_id=res.get("timesheet_id"),
                             html_body=render("Timesheet returned by the client",
                                              [f"{who} returned {res.get('consultant')}'s timesheet for the week of {week}.",
                                               f"Reason: {body}",
                                               "Please ask the consultant to fix it; it comes back to you for approval afterwards."],
                                              button=("Open timesheets", f"{settings.web_origin.rstrip('/')}/timesheets")))
        if res.get("consultant_email"):
            await send_email(db, to=res["consultant_email"], subject=f"Your timesheet was returned — week of {week}",
                             kind="timesheet", tenant_id=res.get("tenant_id"), ref_type="timesheet",
                             ref_id=res.get("timesheet_id"),
                             html_body=render("Timesheet returned for changes",
                                              [f"Your timesheet for the week of {week} was returned by {who}.",
                                               f"Reason: {body}"],
                                              button=("Fix and resubmit", f"{settings.web_origin.rstrip('/')}/my/timesheet")))


@router.get("/{timesheet_id}")
async def review(timesheet_id: UUID, db: TenantDb = Depends(tenant_db)):
    ts = await db.one(
        """select t.*, c.full_name, c.engagement, emp.name as employer from timesheets t
             join consultants c on c.id = t.consultant_id left join companies emp on emp.id = c.employer_company_id
            where t.id = :id""", {"id": timesheet_id})
    if ts is None:
        raise not_found("Timesheet")
    lines = await db.all(
        """select e.placement_id, coalesce(pr.name, 'Internal / non-billable') as project, e.work_date, e.hours,
                  p.bill_rate, p.pay_rate, ar.name as ar_company, coalesce(ap.name, apc.full_name) as ap_payee
             from timesheet_entries e left join placements p on p.id = e.placement_id left join projects pr on pr.id = p.project_id
             left join companies ar on ar.id = p.ar_company_id left join companies ap on ap.id = p.ap_company_id
             left join consultants apc on apc.id = p.ap_consultant_id
            where e.timesheet_id = :id order by project, e.work_date""", {"id": timesheet_id})
    rows: dict[str, dict] = {}
    preview = {"ar": Decimal(0), "ap": Decimal(0), "ar_to": set(), "ap_to": set()}
    for line in lines:
        key = str(line["placement_id"])
        row = rows.setdefault(key, {"placement_id": line["placement_id"], "project": line["project"], "hours": [Decimal(0)] * 7})
        row["hours"][(line["work_date"] - ts["week_start"]).days] += Decimal(line["hours"])
        if line["bill_rate"] is not None:
            preview["ar"] += Decimal(line["hours"]) * line["bill_rate"]
            preview["ar_to"].add(line["ar_company"])
        if line["pay_rate"] is not None and line["ap_payee"]:
            preview["ap"] += Decimal(line["hours"]) * line["pay_rate"]
            preview["ap_to"].add(line["ap_payee"])
    checks, summary = await _checks(db, timesheet_id=ts["id"])
    # Approval state for the page: which end-client companies are represented here and
    # whether the week is waiting on them after the placed-by approval.
    end_clients = await _end_clients(db, ts["tenant_id"], timesheet_id)
    result = {**ts, "rows": list(rows.values()), "checks": checks, "summary": summary,
              "end_client_companies": sorted(str(c) for c in end_clients),
              "awaiting_end_client": bool(end_clients) and ts["placed_by_approved"] and not ts["end_client_approved"]}
    if db.ctx.allows("finance"):
        result["creates"] = {"ar_amount": preview["ar"], "ar_to": sorted(x for x in preview["ar_to"] if x),
                             "ap_amount": preview["ap"], "ap_to": sorted(x for x in preview["ap_to"] if x)}
    return result


@router.post("/{timesheet_id}/approve")
async def approve(timesheet_id: UUID, db: TenantDb = Depends(tenant_db)):
    ts = await db.one(
        """select t.id, t.status, t.week_start, t.weekend_confirmed, t.tenant_id, c.full_name as consultant
             from timesheets t join consultants c on c.id = t.consultant_id where t.id = :id""", {"id": timesheet_id})
    if ts is None:
        raise not_found("Timesheet")
    if ts["status"] != "submitted":
        raise ApiError(409, "not_submitted", "Only submitted timesheets can be approved")
    # Weekend hours need the consultant's own confirmation before anyone approves.
    weekend = await _weekend_hours(db, timesheet_id)
    if weekend > 0 and not ts["weekend_confirmed"]:
        raise ApiError(409, "weekend_confirmation_required",
                       "This week has weekend hours. Ask the consultant to confirm them before approving.")

    # "Placed by" is the workspace that owns the timesheet — the company that placed
    # the consultant approves first (its staff). The end client approves second: either
    # in-app (its representative is a member of this workspace) or through a personal
    # approval link sent to its own workspace's timesheet managers. Without any
    # reachable end client, the placing company's approval is final.
    chain = {r["cid"] for r in await db.all(
        """select distinct p.end_client_company_id as cid
             from timesheet_entries e join placements p on p.id = e.placement_id
            where e.timesheet_id = :id and p.end_client_company_id is not null""", {"id": timesheet_id})}
    own = await db.val("select company_id from mytrakin.tenants where id = :t", {"t": ts["tenant_id"]})
    chain.discard(own)
    recipients = await _end_client_recipients(db, ts["tenant_id"], chain)
    end_clients = chain & {r["company_id"] for r in await db.all(
        """select distinct m.company_id from mytrakin.memberships m
            where m.tenant_id = :t and m.status = 'active' and m.company_id is not null""",
        {"t": ts["tenant_id"]})}
    is_placed_by = db.ctx.tenant_id is not None and ts["tenant_id"] == db.ctx.tenant_id
    is_end_client = db.ctx.company_id is not None and db.ctx.company_id in end_clients
    if not is_placed_by and not is_end_client:
        raise ApiError(403, "forbidden", "Your company is not part of this timesheet's placement chain")
    if is_placed_by and not is_end_client:
        db.ctx.require(*APPROVER_ROLES)
    await _contract_gate(db, timesheet_id)

    current = await db.one("select placed_by_approved, end_client_approved from timesheets where id = :id", {"id": timesheet_id})
    if is_placed_by and not is_end_client and current["placed_by_approved"]:
        raise ApiError(409, "already_approved",
                       "Your company already approved this week — no further approval is needed here.")

    new_pb = current["placed_by_approved"] or is_placed_by
    new_ec = current["end_client_approved"] or is_end_client
    # Weeks with no reachable end client finalise on the placing company's approval alone.
    new_status = "approved" if new_pb and (new_ec or not recipients) else "submitted"

    row = await db.one(
        """update timesheets set status = :s, placed_by_approved = :pb, end_client_approved = :ec,
            decided_by = :u, decided_at = now(), reject_reason = null
            where id = :id returning id, status, placed_by_approved, end_client_approved""",
        {"id": timesheet_id, "u": db.ctx.user_id, "s": new_status, "pb": new_pb, "ec": new_ec})
    if new_status == "submitted" and new_pb and not current["placed_by_approved"] and recipients:
        # The placed-by approval just landed — the week flows to the end client's
        # timesheet managers (personal approval links, e-mailed).
        await _send_client_approval(db, ts, recipients, timesheet_id)
    if new_status == "approved":
        # Final approval — this week's AR/AP invoices are generated automatically.
        asyncio.create_task(_auto_invoice(ts["week_start"], ts["tenant_id"], db.ctx.user_id))
    return row


@router.post("/{timesheet_id}/weekend-confirm-request")
async def weekend_confirm_request(timesheet_id: UUID, body: WeekendNote, db: TenantDb = Depends(tenant_db)):
    """Ask the consultant to confirm the weekend hours before the week can be approved."""
    db.ctx.require(*APPROVER_ROLES)
    ts = await db.one(
        """select t.id, t.status, t.week_start, t.consultant_id, c.full_name
             from timesheets t join consultants c on c.id = t.consultant_id where t.id = :id""",
        {"id": timesheet_id})
    if ts is None:
        raise not_found("Timesheet")
    if ts["status"] != "submitted":
        raise ApiError(409, "not_submitted", "The week isn't awaiting approval any more")
    hours = await _weekend_hours(db, timesheet_id)
    if hours <= 0:
        raise bad_request("This timesheet has no weekend hours to confirm")
    note = (body.note or "").strip() or None
    await db.run(
        """update timesheets set weekend_requested_by = :u, weekend_requested_at = now(),
             weekend_review_note = :n, weekend_confirmed = false where id = :id""",
        {"u": db.ctx.user_id, "n": note, "id": timesheet_id})
    # The consultant is notified by e-mail and sees a banner in My timesheet.
    to = await _consultant_email(db, ts["consultant_id"])
    if to:
        settings = get_settings()
        paras = [f"{hours:g} hours are logged on Saturday/Sunday for the week of {ts['week_start']}.",
                 "Your approver asks you to confirm the client requested weekend work."]
        if note:
            paras.append(f"Note from your approver: {note}")
        await send_email(db, to=to, subject=f"Confirm your weekend hours — week of {ts['week_start']}",
                         kind="timesheet", tenant_id=db.ctx.tenant_id, ref_type="timesheet", ref_id=timesheet_id,
                         html_body=render("Please confirm your weekend hours", paras,
                                          button=("Open my timesheet", f"{settings.web_origin.rstrip('/')}/my/timesheet")))
    return {"id": timesheet_id, "weekend_confirmed": False, "requested": True}


@router.post("/mine/weekend-confirm")
async def weekend_confirm(db: TenantDb = Depends(tenant_db), week: date = Query(...)):
    """The consultant confirms the weekend hours their approver asked about."""
    if db.ctx.role != "consultant":
        raise ApiError(403, "forbidden", "Only consultants confirm their weekend hours")
    ws = _sunday(week)
    # One timesheet per project: confirm every submitted project of the week that
    # was asked about (the approver asks per timesheet).
    tss = await db.all(
        """select t.id, t.week_start, t.weekend_confirmed, t.weekend_requested_at, t.weekend_requested_by,
                  c.full_name from timesheets t join consultants c on c.id = t.consultant_id
            where t.consultant_id = :c and t.week_start = :ws and t.status = 'submitted'
            order by t.id""", {"c": db.ctx.consultant_id, "ws": ws})
    if not tss:
        raise ApiError(409, "not_submitted", "This week isn't awaiting approval")
    asked = [t for t in tss if not t["weekend_confirmed"] and t["weekend_requested_at"] is not None]
    if not asked:
        if all(t["weekend_confirmed"] for t in tss):
            return {"id": tss[0]["id"], "weekend_confirmed": True}
        raise bad_request("Your approver hasn't asked you to confirm weekend hours on this week")
    for t in asked:
        await db.run(
            "update timesheets set weekend_confirmed = true, weekend_confirmed_by = :u,"
            " weekend_confirmed_at = now() where id = :id",
            {"u": db.ctx.user_id, "id": t["id"]})
        # Tell the approver who asked, so they can finish the approval.
        to = await _user_email(db, t["weekend_requested_by"])
        if to:
            settings = get_settings()
            await send_email(db, to=to, subject=f"Weekend hours confirmed — week of {t['week_start']}",
                             kind="timesheet", tenant_id=db.ctx.tenant_id, ref_type="timesheet", ref_id=t["id"],
                             html_body=render("Weekend hours confirmed",
                                              [f"{t['full_name']} confirmed the weekend hours for the week of {t['week_start']}.",
                                               "You can approve the week now."],
                                              button=("Review timesheet", f"{settings.web_origin.rstrip('/')}/timesheets/{t['id']}")))
    return {"id": asked[0]["id"], "weekend_confirmed": True}


@router.post("/{timesheet_id}/reject")
async def reject(timesheet_id: UUID, body: Decision, db: TenantDb = Depends(tenant_db)):
    db.ctx.require(*APPROVER_ROLES)
    if not body.reason or len(body.reason.strip()) < 3:
        raise bad_request("Give a reason so the consultant knows what to fix")
    # Invoice generation skips periods that already have an AR invoice, so reopening invoiced hours would lose the change.
    invoiced = await db.val(
        """select string_agg(distinct i.number, ', ') from timesheet_entries e
             join invoices i on i.placement_id = e.placement_id and i.direction = 'ar' and i.status <> 'void'
                            and i.period_start <= e.work_date and i.period_end >= e.work_date
            where e.timesheet_id = :id""", {"id": timesheet_id})
    if invoiced:
        # TS-07: once billed, the correction is on the invoice — a credit note for fewer hours, an extra invoice for more.
        raise ApiError(409, "already_invoiced", f"These hours are already invoiced ({invoiced}). Void the invoice if nothing "
                                                "is paid to re-open the week, or record the difference as a credit note "
                                                "(fewer hours) or an extra invoice (more hours).")
    row = await db.one(
        """update timesheets set status = 'rejected', decided_by = :u, decided_at = now(), reject_reason = :r,
            placed_by_approved = false, end_client_approved = false, weekend_confirmed = false,
            weekend_requested_by = null, weekend_requested_at = null, weekend_review_note = null
            where id = :id and status in ('submitted', 'approved') returning id, status""",
        {"id": timesheet_id, "u": db.ctx.user_id, "r": body.reason.strip()})
    if row is None:
        raise not_found("Timesheet")
    # The consultant is told what to fix, by e-mail and in My timesheet.
    info = await db.one(
        "select week_start, consultant_id from timesheets where id = :id", {"id": timesheet_id})
    to = await _consultant_email(db, info["consultant_id"])
    if to:
        settings = get_settings()
        await send_email(db, to=to, subject=f"Your timesheet was returned — week of {info['week_start']}",
                         kind="timesheet", tenant_id=db.ctx.tenant_id, ref_type="timesheet", ref_id=timesheet_id,
                         html_body=render("Timesheet returned for changes",
                                          [f"Your timesheet for the week of {info['week_start']} was returned.",
                                           f"Reason: {body.reason.strip()}"],
                                          button=("Fix and resubmit", f"{settings.web_origin.rstrip('/')}/my/timesheet")))
    return row


@router.post("/approve-passing")
async def approve_all_passing(db: TenantDb = Depends(tenant_db), week: date = Query(...)):
    """Approve every submitted timesheet for the week whose checks all pass."""
    db.ctx.require(*APPROVER_ROLES)
    ws = _sunday(week)
    # Get all submitted timesheets for this week with consultant info
    tss = await db.all(
        """select t.id, c.full_name as consultant
             from timesheets t
             join consultants c on c.id = t.consultant_id
            where t.week_start = :ws and t.status = 'submitted' and not t.placed_by_approved""",
        {"ws": ws})
    approved, skipped = [], []
    for ts in tss:
        try:
            checks, summary = await _checks(db, timesheet_id=ts["id"])
            if checks and summary.get("result") != "pass":
                skipped.append(f"{ts['consultant']}: checks failed")
                continue
            await approve(ts["id"], db)
            approved.append(ts["consultant"])
        except ApiError as exc:     # contract / acceptance missing: leave it for review
            skipped.append(f"{ts['consultant']}: {exc.message}")
            continue
    return {"approved": approved, "skipped": skipped}
