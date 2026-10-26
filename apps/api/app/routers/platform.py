"""Platform admin console (the company running myTrakIn as SaaS): every company, the
activation queue, platform admins, and platform-wide analytics (aggregates only)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, EmailStr, Field

from ..config import get_settings
from ..deps import TenantDb, platform_db
from ..errors import ApiError, bad_request, conflict, not_found
from ..services import storage
from ..services.email import render, send_email
from . import companies as companies_router
from .admin import sync_company_owner

router = APIRouter(prefix="/platform", tags=["platform"])

# List price per active user per month. Change here (or move to a table) when pricing changes.
PRICE_PER_USER = {"starter": Decimal("12"), "growth": Decimal("20"), "enterprise": Decimal("32")}
TRIAL_DAYS = 30


async def _tenants(db: TenantDb) -> list[dict]:
    rows = await db.all(
        """select t.id, t.name, t.legal_name, t.state, t.plan, t.status, t.onboarding_step, t.trial_ends_on, t.live_on,
                  t.created_at, t.activated_at, s.active_users, s.invited_users, s.consultants, s.active_placements,
                  s.last_user_activity, ms.ar_invoiced, ms.ar_collected, ms.ap_billed, ms.ap_paid,
                  ms.invoiced_30d, ms.collected_30d
             from tenants t join mytrakin.platform_tenant_stats() s on s.tenant_id = t.id
             join mytrakin.platform_money_stats() ms on ms.tenant_id = t.id
            order by t.created_at desc""")
    for r in rows:
        billable = r["status"] == "active" and not (r["trial_ends_on"] and r["trial_ends_on"] >= date.today())
        r["mrr"] = PRICE_PER_USER[r["plan"]] * r["active_users"] if billable else Decimal(0)
        r["price_per_user"] = PRICE_PER_USER[r["plan"]]
    return rows


@router.get("/metrics")
async def metrics(db: TenantDb = Depends(platform_db)):
    """Everything on the platform dashboard: people, companies, the onboarding pipeline, our SaaS revenue
    and the money moving through myTrakIn (totals only)."""
    tenants = await _tenants(db)
    o = await db.one("select * from mytrakin.platform_overview()")
    trend = await db.all("select * from mytrakin.platform_money_trend()")
    pending = await db.val(
        "select count(*) from mytrakin.platform_companies() where status = 'onboarding' and company_id is not null")
    by = {s: sum(1 for t in tenants if t["status"] == s) for s in ("onboarding", "active", "suspended", "rejected", "closed")}
    paying = [t for t in tenants if t["mrr"] > 0]
    mrr = sum((t["mrr"] for t in tenants), Decimal(0))

    def tot(k: str) -> Decimal:
        return sum((t[k] for t in tenants), Decimal(0))

    month_ago, two_weeks_ago = date.today() - timedelta(days=30), date.today() - timedelta(days=14)
    return {
        "users": {"total": o["total_users"], "new_30d": o["new_users_30d"], "active_30d": o["active_users_30d"],
                  "active_in_companies": sum(t["active_users"] for t in tenants)},
        "companies": {"total": len(tenants), "active": by["active"], "pending_activation": pending,
                      "suspended": by["suspended"], "rejected": by["rejected"], "closed": by["closed"],
                      "new_30d": sum(1 for t in tenants if t["created_at"].date() >= month_ago),
                      "inactive_14_days": [t["name"] for t in tenants if t["status"] == "active" and
                                           (t["last_user_activity"] is None or t["last_user_activity"].date() < two_weeks_ago)]},
        "pipeline": [{"stage": "Wizard in progress", "count": o["wizards_in_progress"]},
                     {"stage": "Waiting for activation", "count": pending},
                     {"stage": "Active", "count": by["active"]},
                     {"stage": "Suspended / closed", "count": by["suspended"] + by["closed"]}],
        "revenue": {"mrr": mrr, "arr": mrr * 12, "paying_companies": len(paying),
                    "arpu": (mrr / sum(t["active_users"] for t in paying)).quantize(Decimal("0.01")) if paying else Decimal(0),
                    "by_plan": {p: sum((t["mrr"] for t in tenants if t["plan"] == p), Decimal(0)) for p in PRICE_PER_USER}},
        "money": {"ar_invoiced": tot("ar_invoiced"), "ar_collected": tot("ar_collected"),
                  "ar_outstanding": tot("ar_invoiced") - tot("ar_collected"),
                  "ap_billed": tot("ap_billed"), "ap_paid": tot("ap_paid"),
                  "invoiced_30d": tot("invoiced_30d"), "collected_30d": tot("collected_30d"), "trend": trend},
        "activity": {"consultants": sum(t["consultants"] for t in tenants),
                     "active_placements": sum(t["active_placements"] for t in tenants)},
        "growth": await db.all(
            """select to_char(date_trunc('month', created_at), 'YYYY-MM') as month, count(*) as new_companies
                 from tenants where created_at > now() - interval '12 months' group by 1 order by 1"""),
    }


@router.get("/tenants")
async def tenants(db: TenantDb = Depends(platform_db)):
    return await _tenants(db)


class TenantPatch(BaseModel):
    plan: str | None = Field(None, pattern="^(starter|growth|enterprise)$")
    status: str | None = Field(None, pattern="^(onboarding|active|suspended|rejected|closed)$")
    trial_ends_on: date | None = None


@router.patch("/tenants/{tenant_id}")
async def update_tenant(tenant_id: UUID, body: TenantPatch, db: TenantDb = Depends(platform_db)):
    """Change plan, extend a trial, suspend (users can't sign in) or close a company."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise bad_request("Nothing to change")
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    row = await db.one(f"update tenants set {sets} where id = :id returning *", {**fields, "id": tenant_id})
    if row is None:
        raise not_found("Tenant")
    return row


# ---------------------------------------------------------------------------- companies & activation
async def _enter(db: TenantDb, tenant_id: UUID) -> None:
    """Act inside one company as 'system' for a platform action (audited with the platform user's id)."""
    await db.run("select mytrakin.begin_request(:u, :t, 'system', null, null, :ip, :ua)",
                 {"u": db.ctx.user_id, "t": tenant_id, "ip": db.ctx.ip, "ua": db.ctx.user_agent})


async def _leave(db: TenantDb) -> None:
    await db.run("select mytrakin.begin_request(:u, null, 'platform_admin', null, null, :ip, :ua)",
                 {"u": db.ctx.user_id, "ip": db.ctx.ip, "ua": db.ctx.user_agent})


@router.get("/companies")
async def companies(db: TenantDb = Depends(platform_db), status: str | None = None):
    """Every company on myTrakIn. status=pending -> registered and waiting for activation."""
    rows = await db.all("select * from mytrakin.platform_companies() order by created_at desc")
    if status == "pending":
        return [r for r in rows if r["status"] == "onboarding" and r["company_id"] is not None]
    return [r for r in rows if status is None or r["status"] == status]


@router.get("/companies/{tenant_id}")
async def company_review(tenant_id: UUID, db: TenantDb = Depends(platform_db)):
    """What the platform needs to decide: the company's onboarding record, W-9 and verification checks."""
    tenant = await db.one("select * from tenants where id = :id", {"id": tenant_id})
    if tenant is None or tenant["company_id"] is None:
        raise not_found("Company")
    await _enter(db, tenant_id)
    company = await companies_router._company_or_404(db, tenant["company_id"])
    checks = await companies_router._run_verification(db, company)
    path = company.get("w9_document_id") and await db.val(
        "select storage_path from documents where id = :d", {"d": company["w9_document_id"]})
    # Every attached file (restricted compliance docs included — the platform may see them).
    drows = await db.all(
        """select id, name, storage_path, restricted from documents
            where owner_type = 'company' and owner_id = :o and deleted_at is null
            order by created_at desc limit 50""", {"o": company["id"]})
    await _leave(db)
    w9_url = await storage.signed_url("documents", path) if path else None
    files = [{"id": str(r["id"]), "name": r["name"], "restricted": r["restricted"],
              "url": await storage.signed_url("documents", r["storage_path"])} for r in drows]
    keep = ("id", "business_code", "name", "kind", "country", "state", "address", "domain", "dba", "business_type",
            "contact_name", "contact_email", "tin", "cin", "tax_classification", "tax_address", "w9_data",
            "w9_status", "w9_document_id", "status", "created_at")
    return {"tenant": tenant, "company": {k: company.get(k) for k in keep}, "w9_url": w9_url, "files": files, **checks}


class CompanyDecision(BaseModel):
    decision: str = Field(pattern="^(activate|needs_info|reject)$")
    note: str | None = Field(None, max_length=1000)


@router.post("/companies/{tenant_id}/compliance-docs", status_code=201)
async def upload_compliance_doc(tenant_id: UUID, file: UploadFile = File(),
                                kind: str = Form(), db: TenantDb = Depends(platform_db)):
    """Platform upload of a restricted government document for a company:
    the W-9 (so a manually-onboarded company can add it before activation),
    tax certificate, certificate of good standing or another government-authorised
    certificate. Only the platform and that company's super admin can view it."""
    tenant = await db.one("select company_id from tenants where id = :id", {"id": tenant_id})
    if tenant is None or tenant["company_id"] is None:
        raise not_found("Company")
    await _enter(db, tenant_id)
    try:
        return await companies_router.upload_compliance_doc(tenant["company_id"], kind=kind, file=file, db=db)
    finally:
        await _leave(db)


class RestrictDocIn(BaseModel):
    file_id: UUID


@router.post("/companies/{tenant_id}/restrict-doc")
async def restrict_doc(tenant_id: UUID, body: RestrictDocIn, db: TenantDb = Depends(platform_db)):
    """Mark an existing company attachment as restricted (a government document) so
    only the platform and that company's super admin / owners can view it."""
    tenant = await db.one("select company_id from tenants where id = :id", {"id": tenant_id})
    if tenant is None or tenant["company_id"] is None:
        raise not_found("Company")
    await _enter(db, tenant_id)
    try:
        if await db.run(
                """update documents set restricted = true
                    where id = :f and owner_type = 'company' and owner_id = :o and deleted_at is null""",
                {"f": body.file_id, "o": tenant["company_id"]}) == 0:
            raise not_found("File")
        return {"id": body.file_id, "restricted": True}
    finally:
        await _leave(db)


@router.post("/companies/{tenant_id}/decision")
async def decide_company(tenant_id: UUID, body: CompanyDecision, db: TenantDb = Depends(platform_db)):
    """Activate a new company, ask its owner for more, or reject it (the owner can fix and resubmit). The owner is e-mailed."""
    tenant = await db.one("select * from tenants where id = :id for update", {"id": tenant_id})
    if tenant is None or tenant["company_id"] is None:
        raise not_found("Company")
    if tenant["status"] != "onboarding":
        raise conflict(f"This company is already {tenant['status']}")
    if body.decision != "activate" and not body.note:
        raise bad_request("Add a note so the owner knows why")
    owner_email = await db.val(
        """select coalesce(p.email, m.invited_email::text) from memberships m
             left join profiles p on p.id = m.user_id where m.id = :m""", {"m": tenant["owner_membership_id"]})
    if body.decision == "activate":
        await _enter(db, tenant_id)
        # The platform reviewed the W-9 on the review screen: that is the staff verification.
        await db.run("""update companies set w9_status = 'verified', w9_decided_at = now(), w9_decided_by = :u
                         where id = :c and w9_status in ('submitted', 'under_review')""",
                     {"u": db.ctx.user_id, "c": tenant["company_id"]})
        company = await companies_router._company_or_404(db, tenant["company_id"])
        result = await companies_router._run_verification(db, company)
        if result["blockers"]:
            raise ApiError(422, "verification_failed", "Can't activate yet: " + "; ".join(result["blockers"]))
        await db.run("update companies set status = 'active', onboarding_stage = 8, verified_at = now() where id = :c",
                     {"c": tenant["company_id"]})
        await _leave(db)
    new_status = {"activate": "active", "needs_info": "onboarding", "reject": "rejected"}[body.decision]
    await db.run(
        """update tenants set status = :s, decision_note = :n,
                  activated_at = case when :s = 'active' then now() end,
                  activated_by = case when :s = 'active' then cast(:u as uuid) end,
                  trial_ends_on = case when :s = 'active' then current_date + cast(:trial as int) else trial_ends_on end
            where id = :id""",
        {"s": new_status, "n": body.note, "u": db.ctx.user_id, "trial": TRIAL_DAYS, "id": tenant_id})
    if owner_email:
        login = f"{get_settings().web_origin.rstrip('/')}/login?email={owner_email}"
        lines = {"activate": [f"{tenant['name']} is now active on myTrakIn. Your {TRIAL_DAYS}-day trial starts today."],
                 "needs_info": ["We need a little more before we can activate your company:", body.note or ""],
                 "reject": ["We're not able to activate this company on myTrakIn.", body.note or ""]}[body.decision]
        await send_email(None, to=owner_email, subject=f"{tenant['name']} on myTrakIn", kind="welcome",
                         html_body=render(f"About {tenant['name']}", lines, button=("Open myTrakIn", login)))
    return {"tenant_id": tenant_id, "status": new_status}


class OwnerIn(BaseModel):
    email: EmailStr


@router.post("/companies/{tenant_id}/owner")
async def set_owner(tenant_id: UUID, body: OwnerIn, db: TenantDb = Depends(platform_db)):
    """Support action when an owner has left: make an existing active staff user the owner (audited)."""
    await _enter(db, tenant_id)
    m = await db.one("""select m.id, m.user_id from memberships m join profiles p on p.id = m.user_id
                         where p.email = :e and m.status = 'active'""", {"e": body.email})
    if m is None:
        raise bad_request("That person isn't an active user of this company")
    await db.run("update memberships set role = 'tenant_admin' where id = :m", {"m": m["id"]})
    company_id = await db.val("update tenants set owner_membership_id = :m where id = :t returning company_id",
                              {"m": m["id"], "t": tenant_id})
    await sync_company_owner(db, tenant_id, company_id, m["user_id"])
    await _leave(db)
    return {"tenant_id": tenant_id, "owner_membership_id": m["id"]}


# ---------------------------------------------------------------------------- platform admins
@router.get("/admins")
async def admins(db: TenantDb = Depends(platform_db)):
    return await db.all("""select pa.user_id, p.email, p.full_name from platform_admins pa
                             join profiles p on p.id = pa.user_id order by p.email""")


class AdminIn(BaseModel):
    email: EmailStr


@router.post("/admins", status_code=201)
async def add_admin(body: AdminIn, db: TenantDb = Depends(platform_db)):
    uid = await db.val("select id from profiles where email = :e", {"e": body.email})
    if uid is None:
        raise bad_request("This person has to sign in to myTrakIn once before they can be made a platform admin")
    await db.run("insert into platform_admins (user_id) values (:u) on conflict do nothing", {"u": uid})
    return {"user_id": uid, "email": body.email}


@router.delete("/admins/{user_id}")
async def remove_admin(user_id: UUID, db: TenantDb = Depends(platform_db)):
    if user_id == db.ctx.user_id:
        raise bad_request("You can't remove yourself — ask another platform admin")
    if await db.run("delete from platform_admins where user_id = :u", {"u": user_id}) == 0:
        raise not_found("Platform admin")
    return {"user_id": user_id, "removed": True}
