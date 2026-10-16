"""Consultants: onboarding (W-2 full-time, W-2 contract, C2C, 1099), active, and former."""

from __future__ import annotations

from datetime import date
from uuid import UUID

import orjson
from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field

from ..config import get_settings
from ..deps import TenantDb, tenant_db
from ..errors import bad_request, not_found
from ..services import workflow
from ..services.email import render, send_email

router = APIRouter(prefix="/consultants", tags=["consultants"])

CHECKLISTS = {
    "w2_fulltime": ["Offer letter signed", "Form I-9 Section 1 (by day 1)", "Form I-9 Section 2 (within 3 business days)",
                    "E-Verify case created", "W-4 and state withholding", "Direct deposit", "Benefits enrollment",
                    "NDA signed", "Company policies accepted", "Background check", "Projects assigned & timesheet access"],
    "w2_contract": ["Contract employment offer signed", "Form I-9 Section 1 (by day 1)", "Form I-9 Section 2 (within 3 business days)",
                    "E-Verify case created", "W-4 and state withholding", "Direct deposit", "NDA signed",
                    "Company policies accepted", "Background check", "Projects assigned & timesheet access"],
    "c2c": ["Vendor has an active MSA", "Vendor SOW / work order signed", "Employer confirms work authorization",
            "Vendor insurance covers consultant", "NDA signed by consultant", "Company policies accepted",
            "Background check", "Projects assigned & timesheet access"],
    "1099": ["Independent contractor agreement signed", "W-9 received and TIN matched",
             "Classification review (1099 vs W-2) documented", "Certificate of insurance (if required)",
             "NDA signed", "Company policies accepted", "Projects assigned & timesheet access"],
}
# A new engagement type (engagement_types table) uses the checklist of its pay model until it gets its own.
_MODEL_CHECKLIST = {"payroll": "w2_contract", "vendor": "c2c", "self": "1099"}


def checklist_for(code: str, pay_model: str) -> list[dict]:
    return [{"item": item, "done": False} for item in CHECKLISTS.get(code) or CHECKLISTS[_MODEL_CHECKLIST[pay_model]]]


@router.get("/engagement-types")
async def engagement_types(db: TenantDb = Depends(tenant_db)):
    """C2C, E2E (employer-to-employer), 1099, W-2 … — from the engagement_types table."""
    return await db.all("select code, name, pay_model from engagement_types where is_active order by sort, name")


class ConsultantIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str | None = None
    engagement: str = Field(min_length=2, max_length=30)   # a code from engagement_types
    employer_company_id: UUID | None = None
    title: str | None = None
    location: str | None = None
    start_date: date
    skills: list[str] = []


class ConsultantPatch(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=120)
    email: EmailStr | None = None
    phone: str | None = None
    title: str | None = None
    location: str | None = None
    work_auth_type: str | None = None
    work_auth_expires: date | None = None
    i9_status: str | None = None
    everify_status: str | None = None
    skills: list[str] | None = None


class ChecklistItem(BaseModel):
    index: int = Field(ge=0)
    done: bool


class Offboard(BaseModel):
    last_day: date
    reason: str = Field(min_length=2, max_length=200)
    rehire_eligible: bool = True


def _view(row: dict, ctx) -> dict:
    """HR sees work-authorization detail; others see status only."""
    if not ctx.allows("hr", "legal"):
        row.pop("work_auth_type", None)
    return row


@router.get("")
async def list_consultants(db: TenantDb = Depends(tenant_db), status: str | None = None):
    rows = await db.all(
        """select c.id, uc.code as user_code, c.full_name, c.email, c.engagement, c.title, c.location, c.status, c.start_date, c.end_date,
                  c.work_auth_type, c.work_auth_expires, c.i9_status, c.everify_status, c.leave_reason, c.rehire_eligible,
                  emp.name as employer,
                  jsonb_array_length(c.onboarding_checklist) as checklist_total,
                  (select count(*) from jsonb_array_elements(c.onboarding_checklist) x where (x ->> 'done')::boolean) as checklist_done,
                  (select string_agg(distinct pr.name, ', ') from placements p join projects pr on pr.id = p.project_id
                    where p.consultant_id = c.id and p.status in ('active', 'ending', 'onboarding')) as projects,
                  (select count(*) from placements p where p.consultant_id = c.id and p.status in ('active', 'ending')) as active_placements
             from consultants c left join companies emp on emp.id = c.employer_company_id
             left join user_codes uc on uc.user_id = c.user_id
             where (cast(:status as text) is null or c.status = :status)
             order by c.status, c.full_name""",
        {"status": status},
    )
    return [_view(r, db.ctx) for r in rows]


@router.post("", status_code=201)
async def onboard(body: ConsultantIn, db: TenantDb = Depends(tenant_db)):
    """Start onboarding. The checklist depends on the engagement type."""
    db.ctx.require("hr", "account_manager", "legal")
    pay_model = await workflow.pay_model(db, body.engagement)
    if pay_model == "vendor" and body.employer_company_id is None:
        raise bad_request("C2C and E2E consultants need their employer (vendor) company")
    checklist = checklist_for(body.engagement, pay_model)
    consultant = await db.one(
        """insert into consultants (tenant_id, full_name, email, phone, engagement, employer_company_id, title, location,
                                    status, start_date, onboarding_checklist, skills)
           values (:t, :name, :email, :phone, :eng, :emp, :title, :loc, 'onboarding', :start, cast(:cl as jsonb), :skills)
           returning *""",
        {"t": db.ctx.tenant_id, "name": body.full_name.strip(), "email": body.email, "phone": body.phone,
         "eng": body.engagement, "emp": body.employer_company_id if pay_model == "vendor" else None,
         "title": body.title, "loc": body.location, "start": body.start_date, "cl": orjson.dumps(checklist).decode(),
         "skills": body.skills},
    )
    # Invite them to sign in (the membership is claimed automatically at first sign-in).
    # Someone who already has a myTrakIn login (e.g. from another company) is linked right away.
    existing_user = await db.val("select id from profiles where email = :e", {"e": body.email})
    await db.run(
        """insert into memberships (tenant_id, user_id, invited_email, role, consultant_id, title, status)
           values (:t, :u, :e, 'consultant', :c, :title, :status) on conflict do nothing""",
        {"t": db.ctx.tenant_id, "u": existing_user, "e": None if existing_user else body.email, "c": consultant["id"],
         "title": body.title, "status": "active" if existing_user else "invited"},
    )
    if existing_user:
        await db.run("update consultants set user_id = :u where id = :c", {"u": existing_user, "c": consultant["id"]})
    tenant = await db.val("select name from tenants where id = :t", {"t": db.ctx.tenant_id})
    await send_email(db, to=body.email, subject=f"Welcome to {tenant} — your myTrakIn access", kind="invite",
                     tenant_id=db.ctx.tenant_id, ref_type="consultant", ref_id=consultant["id"],
                     html_body=render(f"Welcome, {body.full_name.split()[0]}",
                                      [f"{tenant} uses myTrakIn for timesheets, documents and payment status.",
                                       "Sign in with this e-mail address — we'll send you a one-time code. You'll find your "
                                       "onboarding documents and company policies there."],
                                      button=("Sign in", f"{get_settings().web_origin.rstrip('/')}/login?email={body.email}")))
    return consultant


@router.get("/{consultant_id}")
async def get_consultant(consultant_id: UUID, db: TenantDb = Depends(tenant_db)):
    c = await db.one(
        "select c.*, uc.code as user_code, emp.name as employer from consultants c "
        "left join companies emp on emp.id = c.employer_company_id "
        "left join user_codes uc on uc.user_id = c.user_id where c.id = :id",
        {"id": consultant_id})
    if c is None:
        raise not_found("Consultant")
    c["placements"] = await db.all(
        """select p.id, pr.name as project, p.role_title, p.start_date, p.end_date, p.status, p.hours_per_week
             from placements p join projects pr on pr.id = p.project_id where p.consultant_id = :id order by p.start_date desc""",
        {"id": consultant_id})
    c["documents"] = await db.all("select * from tracked_documents where consultant_id = :id and active order by expires_on", {"id": consultant_id})
    c["agreements"] = await db.all("select id, code, kind, effective_on, expires_on, status from agreements where consultant_id = :id", {"id": consultant_id})
    c["policies"] = await db.all(
        """select po.name, po.version, pa.accepted_at, pa.ip from policies po
             left join policy_acceptances pa on pa.policy_id = po.id and pa.consultant_id = :id
            where po.active and :eng = any (po.applies_to) order by po.name""", {"id": consultant_id, "eng": c["engagement"]})
    c["files"] = await db.all(
        "select id, name, size_bytes, mime_type, created_at from documents where owner_type = 'consultant' and owner_id = :id "
        "and deleted_at is null order by created_at desc", {"id": consultant_id})
    return _view(c, db.ctx)


@router.patch("/{consultant_id}")
async def update_consultant(consultant_id: UUID, body: ConsultantPatch, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("hr", "account_manager", "legal")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return await get_consultant(consultant_id, db)
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    row = await db.one(f"update consultants set {sets} where id = :id returning *", {**fields, "id": consultant_id})
    if row is None:
        raise not_found("Consultant")
    return row


@router.post("/{consultant_id}/checklist")
async def tick_checklist(consultant_id: UUID, body: ChecklistItem, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("hr", "account_manager", "legal")
    row = await db.one(
        """update consultants set onboarding_checklist = jsonb_set(onboarding_checklist, array[cast(:i as text), 'done'], to_jsonb(cast(:done as boolean)))
            where id = :id and :i < jsonb_array_length(onboarding_checklist)
            returning id, onboarding_checklist""",
        {"id": consultant_id, "i": body.index, "done": body.done},
    )
    if row is None:
        raise not_found("Checklist item")
    return row


@router.post("/{consultant_id}/activate")
async def activate(consultant_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Finish onboarding: the consultant becomes active and can submit timesheets."""
    db.ctx.require("hr", "account_manager", "legal")
    c = await db.one("select onboarding_checklist from consultants where id = :id", {"id": consultant_id})
    if c is None:
        raise not_found("Consultant")
    open_items = [x["item"] for x in c["onboarding_checklist"] if not x.get("done")]
    if len(open_items) > 1 or (open_items and "Projects assigned" not in open_items[0]):
        raise bad_request(f"Finish the checklist first: {', '.join(open_items[:3])}")
    await db.run(
        """update consultants set status = 'active',
                  onboarding_checklist = (select jsonb_agg(x || '{"done": true}') from jsonb_array_elements(onboarding_checklist) x)
            where id = :id""", {"id": consultant_id})
    await db.run("update placements set status = 'active' where consultant_id = :id and status = 'onboarding'", {"id": consultant_id})
    return {"id": consultant_id, "status": "active"}


@router.post("/{consultant_id}/offboard")
async def offboard(consultant_id: UUID, body: Offboard, db: TenantDb = Depends(tenant_db)):
    """End all assignments and move the consultant to Former. Nothing is deleted."""
    db.ctx.require("hr", "account_manager", "legal")
    row = await db.one(
        """update consultants set status = 'former', end_date = :d, leave_reason = :r, rehire_eligible = :h
            where id = :id returning id, full_name, status""",
        {"id": consultant_id, "d": body.last_day, "r": body.reason, "h": body.rehire_eligible})
    if row is None:
        raise not_found("Consultant")
    await db.run(
        "update placements set status = 'ended', end_date = least(coalesce(end_date, :d), :d) where consultant_id = :id and status <> 'completed'",
        {"id": consultant_id, "d": body.last_day})
    await db.run("update memberships set status = 'deactivated' where consultant_id = :id", {"id": consultant_id})
    return row


@router.post("/{consultant_id}/rehire")
async def rehire(consultant_id: UUID, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("hr", "account_manager", "legal")
    c = await db.one("select engagement, rehire_eligible from consultants where id = :id and status = 'former'", {"id": consultant_id})
    if c is None:
        raise not_found("Former consultant")
    if c["rehire_eligible"] is False:
        raise bad_request("This person is marked not eligible for rehire")
    checklist = checklist_for(c["engagement"], await workflow.pay_model(db, c["engagement"]))
    await db.run(
        """update consultants set status = 'onboarding', end_date = null, leave_reason = null, start_date = current_date,
                  onboarding_checklist = cast(:cl as jsonb) where id = :id""",
        {"id": consultant_id, "cl": orjson.dumps(checklist).decode()})
    await db.run("update memberships set status = 'active' where consultant_id = :id and user_id is not null", {"id": consultant_id})
    return {"id": consultant_id, "status": "onboarding"}
