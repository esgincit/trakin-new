"""Timesheets: one per consultant per week, one line per project.

Consultants enter and submit; the admin (or an approver) validates against the
automatic checks and approves or rejects with a reason. Approved weeks are locked
and feed invoicing."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator

from ..deps import TenantDb, tenant_db
from ..errors import ApiError, bad_request, not_found
from ..services import workflow
from ..services.timesheet_checks import Entry, PlacementInfo, run_checks, summarize
from ..utils import week_start

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


def _sunday(day: date) -> date:
    if day.weekday() != 6:
        raise bad_request("week_start must be a Sunday")
    return day


async def _checks(db: TenantDb, ts: dict) -> tuple[list, dict]:
    entries = await db.all("select placement_id, work_date, hours from timesheet_entries where timesheet_id = :id", {"id": ts["id"]})
    placements = await db.all(
        """select p.id, p.hours_per_week, p.start_date, p.end_date, p.bill_rate, s.code as sow_code,
                  (s.value_cap - b.invoiced) as sow_remaining
             from placements p left join sows s on s.id = p.ar_sow_id left join sow_burn b on b.sow_id = s.id
            where p.consultant_id = :c and p.start_date <= :we and coalesce(p.end_date, :ws) >= :ws""",
        {"c": ts["consultant_id"], "ws": ts["week_start"], "we": ts["week_start"] + timedelta(days=6)})
    checks = run_checks(
        status=ts["status"],
        week_start=ts["week_start"],
        entries=[Entry(str(e["placement_id"]) if e["placement_id"] else None, e["work_date"], Decimal(e["hours"])) for e in entries],
        placements={str(p["id"]): PlacementInfo(str(p["id"]), Decimal(p["hours_per_week"]), p["start_date"], p["end_date"],
                                                p["bill_rate"], p["sow_code"], p["sow_remaining"]) for p in placements},
        engagement=ts["engagement"],
        show_money=db.ctx.allows("finance"),
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
                    order by o.status = 'active' desc, o.created_at desc limit 1) as offer_status
             from timesheet_entries e join placements p on p.id = e.placement_id join projects pr on pr.id = p.project_id
             join consultants c on c.id = p.consultant_id join engagement_types et on et.code = c.engagement
             left join sows aps on aps.id = p.ap_sow_id left join sows ars on ars.id = p.ar_sow_id
            where e.timesheet_id = :id""", {"id": timesheet_id})
    for r in rows:
        payroll = r["pay_model"] == "payroll"
        contract_status = r["offer_status"] if payroll else r["ap_status"]
        what = "offer letter" if payroll else "vendor / contractor work order"
        if rules["requireContract"] and contract_status is None:
            raise workflow.blocked("contract_required", f"{r['project']}: no {what} for this resource yet — add it before "
                                                        "timesheets (or turn off 'Require contract' in Settings → Workflow)")
        if rules["requireAcceptance"]:
            if contract_status is not None and contract_status != "active":
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
                  t.id, coalesce(t.status, 'not_submitted') as status, t.submitted_at, t.reject_reason, t.note,
                  (select string_agg(distinct pr.name, ', ') from placements p join projects pr on pr.id = p.project_id
                    where p.consultant_id = c.id and p.start_date <= cast(:ws as date) + 6
                      and coalesce(p.end_date, cast(:ws as date)) >= :ws) as projects,
                  coalesce((select array_agg(coalesce(d.h, 0) order by dn) from generate_series(0, 6) dn
                             left join (select (e.work_date - cast(:ws as date)) as dn, sum(e.hours) as h from timesheet_entries e
                                         where e.timesheet_id = t.id group by 1) d using (dn)), '{0,0,0,0,0,0,0}') as days
             from consultants c
             left join companies emp on emp.id = c.employer_company_id
             left join timesheets t on t.consultant_id = c.id and t.week_start = :ws
            where c.status = 'active'
              and (t.id is not null or exists (select 1 from placements p where p.consultant_id = c.id
                                                and p.start_date <= cast(:ws as date) + 6 and coalesce(p.end_date, cast(:ws as date)) >= :ws))
            order by c.full_name""",
        {"ws": ws})
    for r in rows:
        r["total"] = sum((Decimal(h) for h in r["days"]), Decimal(0))
        if r["id"]:
            ts = {"id": r["id"], "consultant_id": r["consultant_id"], "week_start": ws, "status": r["status"], "engagement": r["engagement"]}
            _, r["checks"] = await _checks(db, ts)
        else:
            r["checks"] = None
    return {"week_start": ws, "rows": rows}


@router.get("/history")
async def history(db: TenantDb = Depends(tenant_db), consultant_id: UUID | None = None,
                  since: date | None = Query(None, alias="from"), until: date | None = Query(None, alias="to")):
    """All weeks, one line per consultant, week and project."""
    if not db.ctx.internal and db.ctx.role != "vendor_admin":
        raise ApiError(403, "forbidden", "Use My timesheet for your own history")
    return await db.all(
        """select t.id, t.week_start, t.status, c.full_name, c.id as consultant_id, coalesce(pr.name, 'Internal') as project,
                  sum(e.hours) as hours, t.decided_at
             from timesheets t join consultants c on c.id = t.consultant_id
             join timesheet_entries e on e.timesheet_id = t.id
             left join placements p on p.id = e.placement_id left join projects pr on pr.id = p.project_id
            where (cast(:c as uuid) is null or t.consultant_id = :c)
              and (cast(:f as date) is null or t.week_start >= :f) and (cast(:u as date) is null or t.week_start <= :u)
            group by t.id, c.id, pr.name
            order by t.week_start desc, c.full_name, project
            limit 2000""",
        {"c": consultant_id, "f": since, "u": until})


# ----------------------------------------------------------------------------- consultant
@router.get("/mine")
async def my_week(db: TenantDb = Depends(tenant_db), week: date | None = None):
    if db.ctx.role != "consultant":
        raise ApiError(403, "forbidden", "Only consultants have a personal timesheet")
    ws = _sunday(week) if week else week_start(date.today())
    ts = await db.one("select * from timesheets where consultant_id = :c and week_start = :ws", {"c": db.ctx.consultant_id, "ws": ws})
    projects = await db.all(
        """select p.id as placement_id, pr.name as project, p.role_title, p.hours_per_week
             from placements p join projects pr on pr.id = p.project_id
            where p.consultant_id = :c and p.status in ('active', 'ending', 'onboarding')
              and p.start_date <= cast(:ws as date) + 6 and coalesce(p.end_date, cast(:ws as date)) >= :ws
            order by pr.name""",
        {"c": db.ctx.consultant_id, "ws": ws})
    grid: dict[str | None, list[Decimal]] = defaultdict(lambda: [Decimal(0)] * 7)
    if ts:
        for e in await db.all("select placement_id, work_date, hours from timesheet_entries where timesheet_id = :id", {"id": ts["id"]}):
            grid[str(e["placement_id"]) if e["placement_id"] else None][(e["work_date"] - ws).days] += Decimal(e["hours"])
    rows = [{"placement_id": p["placement_id"], "project": p["project"], "hours": grid.get(str(p["placement_id"]), [Decimal(0)] * 7)}
            for p in projects]
    if None in grid:
        rows.append({"placement_id": None, "project": "Internal / non-billable", "hours": grid[None]})
    # TS-10: approved time off shown per day (read-only, never saved as hours or billed).
    off = await db.all(
        """select starts_on, ends_on, kind from time_off where consultant_id = :c and status in ('approved', 'holiday')
            and starts_on <= cast(:ws as date) + 6 and ends_on >= :ws""", {"c": db.ctx.consultant_id, "ws": ws})
    time_off = [next((o["kind"] for o in off if o["starts_on"] <= ws + timedelta(days=i) <= o["ends_on"]), None) for i in range(7)]
    return {"week_start": ws, "status": ts["status"] if ts else "draft", "reject_reason": ts["reject_reason"] if ts else None,
            "note": ts["note"] if ts else None, "rows": rows, "projects": projects, "time_off": time_off}


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
    ts = await db.one("select id, status, note from timesheets where consultant_id = :c and week_start = :ws", {"c": db.ctx.consultant_id, "ws": ws})
    # Submitted/approved weeks are locked and cannot be edited. Rejected weeks can be
    # edited and resubmitted by the consultant until they are approved.
    if ts and ts["status"] in ("submitted", "approved"):
        raise ApiError(409, "locked", "This week is already submitted. Ask your admin to return it if something needs to change.")
    if ts is None:
        ts = await db.one("insert into timesheets (tenant_id, consultant_id, week_start, note) values (:t, :c, :ws, :n) returning id, status",
                          {"t": db.ctx.tenant_id, "c": db.ctx.consultant_id, "ws": ws, "n": body.note})
    else:
        # Resetting approvals when a rejected timesheet is edited
        await db.run("update timesheets set note = :n, placed_by_approved = false, end_client_approved = false where id = :id",
                     {"n": body.note, "id": ts["id"]})
    await db.run("delete from timesheet_entries where timesheet_id = :id", {"id": ts["id"]})
    entries = [{"t": db.ctx.tenant_id, "ts": ts["id"], "p": row.placement_id, "d": ws + timedelta(days=i), "h": h}
               for row in body.rows for i, h in enumerate(row.hours) if h > 0]
    if entries:
        await db.run("""insert into timesheet_entries (tenant_id, timesheet_id, placement_id, work_date, hours)
                        values (:t, :ts, :p, :d, :h)""", entries)
    return await my_week(db, ws)


@router.post("/mine/submit")
async def submit_my_week(body: Decision, db: TenantDb = Depends(tenant_db), week: date = Query(...)):
    if db.ctx.role != "consultant":
        raise ApiError(403, "forbidden", "Only consultants submit timesheets")
    ws = _sunday(week)
    ts = await db.one("select id, status, note from timesheets where consultant_id = :c and week_start = :ws", {"c": db.ctx.consultant_id, "ws": ws})
    if ts is None:
        raise bad_request("Enter your hours first")
    if not ts["note"] or not ts["note"].strip():
        raise bad_request("Please enter a note before submitting the timesheet.")
    total = await db.val("select coalesce(sum(hours), 0) from timesheet_entries where timesheet_id = :id", {"id": ts["id"]})
    if total <= 0:
        raise bad_request("Enter your hours first")
    await _contract_gate(db, ts["id"])
    await db.run("update timesheets set status = 'submitted', submitted_at = now(), reject_reason = null, placed_by_approved = false, end_client_approved = false where id = :id", {"id": ts["id"]})
    return {"id": ts["id"], "status": "submitted"}


# ----------------------------------------------------------------------------- review
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
    checks, summary = await _checks(db, ts)
    result = {**ts, "rows": list(rows.values()), "checks": checks, "summary": summary}
    if db.ctx.allows("finance"):
        result["creates"] = {"ar_amount": preview["ar"], "ar_to": sorted(x for x in preview["ar_to"] if x),
                             "ap_amount": preview["ap"], "ap_to": sorted(x for x in preview["ap_to"] if x)}
    return result


@router.post("/{timesheet_id}/approve")
async def approve(timesheet_id: UUID, db: TenantDb = Depends(tenant_db)):
    db.ctx.require(*APPROVER_ROLES)
    await _contract_gate(db, timesheet_id)
    ts = await db.one("select id, status from timesheets where id = :id", {"id": timesheet_id})
    if ts is None:
        raise not_found("Timesheet")
    if ts["status"] != "submitted":
        raise ApiError(409, "not_submitted", "Only submitted timesheets can be approved")

    # Determine which companies are on this timesheet's placement chain
    placements = await db.all("""
        select distinct p.end_client_company_id as end_client_id, p.ap_company_id as placed_by_id
        from timesheet_entries e
        join placements p on p.id = e.placement_id
        where e.timesheet_id = :id
    """, {"id": timesheet_id})
    end_client_ids = {r["end_client_id"] for r in placements if r["end_client_id"]}
    placed_by_ids = {r["placed_by_id"] for r in placements if r["placed_by_id"]}

    approver_company_id = db.ctx.company_id
    is_placed_by = approver_company_id in placed_by_ids
    is_end_client = approver_company_id in end_client_ids

    if not is_placed_by and not is_end_client:
        raise ApiError(403, "forbidden", "Your company is not part of this timesheet's placement chain")

    current = await db.one("select placed_by_approved, end_client_approved from timesheets where id = :id", {"id": timesheet_id})

    new_pb = current["placed_by_approved"] or is_placed_by
    new_ec = current["end_client_approved"] or is_end_client
    new_status = "approved" if new_pb and new_ec else "submitted"

    row = await db.one(
        """update timesheets set status = :s, placed_by_approved = :pb, end_client_approved = :ec,
            decided_by = :u, decided_at = now(), reject_reason = null
            where id = :id returning id, status, placed_by_approved, end_client_approved""",
        {"id": timesheet_id, "u": db.ctx.user_id, "s": new_status, "pb": new_pb, "ec": new_ec})
    return row


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
            placed_by_approved = false, end_client_approved = false
            where id = :id and status in ('submitted', 'approved') returning id, status""",
        {"id": timesheet_id, "u": db.ctx.user_id, "r": body.reason.strip()})
    if row is None:
        raise not_found("Timesheet")
    return row


@router.post("/approve-passing")
async def approve_all_passing(db: TenantDb = Depends(tenant_db), week: date = Query(...)):
    """Approve every submitted timesheet for the week whose checks all pass."""
    db.ctx.require(*APPROVER_ROLES)
    overview = await week_overview(db, _sunday(week))
    approved, skipped = [], []
    for r in overview["rows"]:
        if r["status"] == "submitted" and r["checks"] and r["checks"]["result"] == "pass":
            try:
                await approve(r["id"], db)
            except ApiError as exc:     # contract / acceptance missing: leave it for review
                skipped.append(f"{r['full_name']}: {exc.message}")
                continue
            approved.append(r["full_name"])
    return {"approved": approved, "skipped": skipped}
