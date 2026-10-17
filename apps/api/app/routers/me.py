"""Who am I, which workspaces can I open, and the consultant's self-service data.

Consultants see their own projects, chain, SOW dates, work authorization, policies
and payment progress — never amounts or rates."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..deps import TenantDb, tenant_db, user_db
from ..errors import ApiError, bad_request, not_found
from ..services import storage

router = APIRouter(tags=["me"])


@router.get("/me")
async def me(db: TenantDb = Depends(user_db)):
    """Profile, the workspaces this person can open, and whether they own the platform."""
    uid = db.ctx.user_id
    profile = await db.one(
        """select p.id, p.email, p.full_name, p.headline, p.avatar_path, p.preferences, uc.code as user_code
             from profiles p left join user_codes uc on uc.user_id = p.id where p.id = :u""", {"u": uid})
    if profile is not None and profile.get("avatar_path"):
        profile["avatar_url"] = storage.public_url("avatars", profile["avatar_path"])
    elif profile is not None:
        profile["avatar_url"] = None
    tenants = await db.all("select * from mytrakin.my_tenants(:u)", {"u": uid})
    is_admin = await db.val("select mytrakin.is_platform_admin_user(:u)", {"u": uid})
    mfa_allowed = await db.val("select mytrakin.mfa_allowed_for(:u)", {"u": uid})
    return {"profile": profile, "tenants": tenants, "is_platform_admin": bool(is_admin), "mfa_allowed": bool(mfa_allowed)}


@router.get("/my/businesses")
async def my_businesses(db: TenantDb = Depends(user_db)):
    """Every business the caller created or belongs to — any role, any workspace.
    Company data itself stays shielded; open a profile to see what your role allows."""
    return await db.all("select * from mytrakin.my_businesses(:u)", {"u": db.ctx.user_id})


@router.get("/session")
async def session(db: TenantDb = Depends(tenant_db)):
    """The caller's role in the selected workspace (drives navigation in the web app)."""
    ctx = db.ctx
    tenant = await db.one("select id, name, plan, status, company_id from tenants where id = :t", {"t": ctx.tenant_id})
    return {
        "tenant": tenant,
        "role": ctx.role,
        "company_id": ctx.company_id,
        "consultant_id": ctx.consultant_id,
        "membership_id": ctx.membership_id,
        "is_platform_admin": ctx.is_platform_admin,
        "is_owner": ctx.is_owner,
        "permissions": ctx.permissions,
        "custom_role": ctx.extra.get("custom_role"),
        "can": {
            "see_money": ctx.allows("finance"),
            "see_bill_rate": ctx.sees_bill_rate,
            "see_pay_rate": ctx.sees_pay_rate,
            "approve_timesheets": ctx.allows("approver", "account_manager", "hr", "finance"),
            "manage_contracts": ctx.allows("legal", "account_manager"),
            "manage_people": ctx.allows("hr", "account_manager", "legal"),
            "manage_users": ctx.allows("tenant_admin"),
            "import_data": ctx.allows("finance", "hr", "legal"),
        },
    }


def _require_consultant(db: TenantDb) -> UUID:
    if db.ctx.role != "consultant" or db.ctx.consultant_id is None:
        raise ApiError(403, "forbidden", "This page is for consultants")
    return db.ctx.consultant_id


@router.get("/me/consultant")
async def my_consultant_overview(db: TenantDb = Depends(tenant_db)):
    """Everything a consultant may see about themselves — no amounts, no rates."""
    cid = _require_consultant(db)
    me_row = await db.one(
        """select c.id, c.full_name, c.email, c.engagement, c.title, c.location, c.status, c.start_date,
                  c.work_auth_type, c.work_auth_expires, c.i9_status, c.everify_status, emp.name as employer
             from consultants c left join companies emp on emp.id = c.employer_company_id
            where c.id = :c""",
        {"c": cid},
    )
    projects = await db.all(
        """select p.id as placement_id, p.role_title, p.start_date, p.end_date, p.status, p.hours_per_week,
                  pr.name as project, pr.description, ec.name as end_client, ar.name as customer, ap.name as payee_company,
                  p.ap_consultant_id is not null as paid_directly, p.ap_terms, p.pay_when_paid,
                  coalesce(aps.code, ars.code) as governing_sow, coalesce(aps.start_date, ars.start_date) as sow_start,
                  coalesce(aps.end_date, ars.end_date) as sow_end,
                  (select a.summary || ' (' || a.status || ')' from sow_amendments a
                    where a.sow_id in (p.ar_sow_id, p.ap_sow_id) and a.status in ('draft', 'out_for_signature')
                    order by a.created_at desc limit 1) as pending_extension
             from placements p
             join projects pr on pr.id = p.project_id
             left join companies ec on ec.id = p.end_client_company_id
             left join companies ar on ar.id = p.ar_company_id
             left join companies ap on ap.id = p.ap_company_id
             left join sows ars on ars.id = p.ar_sow_id
             left join sows aps on aps.id = p.ap_sow_id
            where p.consultant_id = :c
            order by p.status = 'active' desc, p.start_date desc""",
        {"c": cid},
    )
    # Payment progress per billing period: statuses and dates only.
    periods = await db.all(
        """select ar.period_start, ar.period_end, ar.hours, pr.name as project, ar.issued_on, ar.due_on,
                  ar.live_status as customer_status,
                  (select max(paid_on) from payments where invoice_id = ar.id and status in ('completed', 'confirmed')) as customer_paid_on,
                  ap.live_status as payee_status, ap.scheduled_on as payee_scheduled_on, ap.due_on as payee_due_on,
                  (select max(paid_on) from payments where invoice_id = ap.id and status in ('completed', 'confirmed')) as payee_paid_on,
                  cust.name as customer, payee.name as payee
             from invoice_balances ar
             join placements p on p.id = ar.placement_id
             join projects pr on pr.id = p.project_id
             left join companies cust on cust.id = ar.company_id
             left join invoice_balances ap on ap.placement_id = ar.placement_id and ap.direction = 'ap'
                                            and ap.period_start = ar.period_start and ap.status <> 'void'
             left join companies payee on payee.id = ap.company_id
            where ar.direction = 'ar' and ar.status <> 'void' and p.consultant_id = :c
            order by ar.period_start desc
            limit 24""",
        {"c": cid},
    )
    documents = await db.all(
        "select id, doc_type, label, expires_on, status from tracked_documents where consultant_id = :c and active order by expires_on",
        {"c": cid},
    )
    policies = await db.all(
        """select po.id, po.name, po.version, po.effective_on, pa.accepted_at
             from policies po
             left join policy_acceptances pa on pa.policy_id = po.id and pa.consultant_id = :c
            where po.active and :eng = any (po.applies_to)
            order by po.name""",
        {"c": cid, "eng": me_row["engagement"] if me_row else ""},
    )
    agreements = await db.all(
        "select id, code, kind, effective_on, expires_on, status from agreements where consultant_id = :c order by effective_on desc",
        {"c": cid},
    )
    to_sign = await db.all(
        """select e.id, e.number, e.title, s.status from envelopes e join envelope_signers s on s.envelope_id = e.id
            where e.consultant_id = :c and e.status = 'sent' and s.status in ('sent', 'viewed')""",
        {"c": cid},
    )
    return {"me": me_row, "projects": projects, "payments": periods, "documents": documents,
            "policies": policies, "agreements": agreements, "to_sign": to_sign}


class AcceptPolicy(BaseModel):
    confirm: bool = True


@router.post("/me/policies/{policy_id}/accept")
async def accept_policy(policy_id: UUID, _: AcceptPolicy, db: TenantDb = Depends(tenant_db)):
    cid = _require_consultant(db)
    await db.run(
        """insert into policy_acceptances (tenant_id, policy_id, consultant_id, ip, user_agent)
           values (:t, :p, :c, :ip, :ua) on conflict (policy_id, consultant_id) do nothing""",
        {"t": db.ctx.tenant_id, "p": policy_id, "c": cid, "ip": db.ctx.ip, "ua": db.ctx.user_agent},
    )
    return {"accepted": True}


@router.get("/me/timesheets")
async def my_timesheet_history(
    db: TenantDb = Depends(tenant_db),
    placement_id: UUID | None = None,
    status: str | None = None,
    since: date | None = Query(None, alias="from"),
    until: date | None = Query(None, alias="to"),
):
    """One line per week and project, newest first. Filter by project, status and dates."""
    cid = _require_consultant(db)
    return await db.all(
        """select t.id as timesheet_id, t.week_start, t.status, e.placement_id,
                  coalesce(pr.name, 'Internal / non-billable') as project, sum(e.hours) as hours, t.decided_at
             from timesheets t
             join timesheet_entries e on e.timesheet_id = t.id
             left join placements p on p.id = e.placement_id
             left join projects pr on pr.id = p.project_id
            where t.consultant_id = :c
              and (cast(:pl as uuid) is null or e.placement_id = :pl)
              and (cast(:st as text) is null or t.status = :st)
              and (cast(:f as date) is null or t.week_start >= :f)
              and (cast(:u as date) is null or t.week_start <= :u)
            group by t.id, e.placement_id, pr.name
            order by t.week_start desc, project""",
        {"c": cid, "pl": placement_id, "st": status, "f": since, "u": until},
    )


class ExpenseIn(BaseModel):
    placement_id: UUID | None = None
    spent_on: date
    category: str = Field(min_length=2, max_length=80)
    amount: Decimal = Field(gt=0, le=Decimal("100000"))
    billable: bool = True


@router.get("/me/expenses")
async def my_expenses(db: TenantDb = Depends(tenant_db)):
    cid = _require_consultant(db)
    return await db.all("select * from expenses where consultant_id = :c order by spent_on desc", {"c": cid})


@router.post("/me/expenses", status_code=201)
async def submit_expense(body: ExpenseIn, db: TenantDb = Depends(tenant_db)):
    cid = _require_consultant(db)
    if body.spent_on > date.today():
        raise bad_request("The expense date can't be in the future")
    return await db.one(
        """insert into expenses (tenant_id, consultant_id, placement_id, spent_on, category, amount, billable)
           values (:t, :c, :p, :d, :cat, :a, :b) returning *""",
        {"t": db.ctx.tenant_id, "c": cid, "p": body.placement_id, "d": body.spent_on, "cat": body.category,
         "a": body.amount, "b": body.billable},
    )


class TimeOffIn(BaseModel):
    starts_on: date
    ends_on: date
    kind: str = Field(pattern="^(pto|sick|unpaid)$")
    note: str | None = Field(None, max_length=500)


@router.get("/me/time-off")
async def my_time_off(db: TenantDb = Depends(tenant_db)):
    cid = _require_consultant(db)
    return await db.all("select * from time_off where consultant_id = :c order by starts_on desc", {"c": cid})


@router.post("/me/time-off", status_code=201)
async def request_time_off(body: TimeOffIn, db: TenantDb = Depends(tenant_db)):
    cid = _require_consultant(db)
    if body.ends_on < body.starts_on:
        raise bad_request("The end date is before the start date")
    if body.ends_on - body.starts_on > timedelta(days=90):
        raise bad_request("Requests longer than 90 days need HR — please contact them")
    return await db.one(
        """insert into time_off (tenant_id, consultant_id, starts_on, ends_on, kind, note)
           values (:t, :c, :s, :e, :k, :n) returning *""",
        {"t": db.ctx.tenant_id, "c": cid, "s": body.starts_on, "e": body.ends_on, "k": body.kind, "n": body.note},
    )


@router.get("/me/documents/{document_id}/link")
async def my_document_link(document_id: UUID, db: TenantDb = Depends(tenant_db)):
    from ..services import storage

    doc = await db.one("select storage_path from documents where id = :d", {"d": document_id})
    if doc is None:
        raise not_found("Document")
    return {"url": await storage.signed_url("documents", doc["storage_path"])}
