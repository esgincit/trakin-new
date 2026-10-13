"""Platform owner console (the company running myTrakIn as SaaS): tenants, sign-up
approvals, and revenue per user."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field

from ..config import get_settings
from ..deps import TenantDb, platform_db
from ..errors import bad_request, conflict, not_found
from ..services.email import render, send_email

router = APIRouter(prefix="/platform", tags=["platform"])

# List price per active user per month. Change here (or move to a table) when pricing changes.
PRICE_PER_USER = {"starter": Decimal("12"), "growth": Decimal("20"), "enterprise": Decimal("32")}
TRIAL_DAYS = 30


async def _tenants(db: TenantDb) -> list[dict]:
    rows = await db.all(
        """select t.id, t.name, t.legal_name, t.state, t.plan, t.status, t.onboarding_step, t.trial_ends_on, t.live_on,
                  t.created_at, s.active_users, s.invited_users, s.consultants, s.active_placements, s.last_user_activity
             from tenants t join mytrakin.platform_tenant_stats() s on s.tenant_id = t.id
            order by t.created_at desc""")
    for r in rows:
        billable = r["status"] == "active" and not (r["trial_ends_on"] and r["trial_ends_on"] >= date.today())
        r["mrr"] = PRICE_PER_USER[r["plan"]] * r["active_users"] if billable else Decimal(0)
        r["price_per_user"] = PRICE_PER_USER[r["plan"]]
    return rows


@router.get("/metrics")
async def metrics(db: TenantDb = Depends(platform_db)):
    tenants = await _tenants(db)
    paying = [t for t in tenants if t["mrr"] > 0]
    users = sum(t["active_users"] for t in tenants)
    mrr = sum((t["mrr"] for t in tenants), Decimal(0))
    month_ago = date.today() - timedelta(days=30)
    signups = await db.all("select status, count(*) as n from tenant_signups group by status")
    growth = await db.all(
        """select to_char(date_trunc('month', created_at), 'YYYY-MM') as month, count(*) as new_tenants
             from tenants where created_at > now() - interval '12 months' group by 1 order by 1""")
    return {
        "tenants": len(tenants),
        "by_status": {s: sum(1 for t in tenants if t["status"] == s) for s in ("onboarding", "active", "suspended", "closed")},
        "active_users": users,
        "paying_tenants": len(paying),
        "mrr": mrr,
        "arr": mrr * 12,
        "arpu": (mrr / sum(t["active_users"] for t in paying)).quantize(Decimal("0.01")) if paying else Decimal(0),
        "new_last_30_days": sum(1 for t in tenants if t["created_at"].date() >= month_ago),
        "inactive_14_days": [t["name"] for t in tenants if t["status"] == "active" and
                             (t["last_user_activity"] is None or t["last_user_activity"].date() < date.today() - timedelta(days=14))],
        "signups": {r["status"]: r["n"] for r in signups},
        "growth": growth,
    }


@router.get("/tenants")
async def tenants(db: TenantDb = Depends(platform_db)):
    return await _tenants(db)


class TenantIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    legal_name: str | None = None
    ein: str | None = Field(None, pattern=r"^\d{2}-?\d{7}$")
    state: str | None = Field(None, max_length=2)
    plan: str = Field("growth", pattern="^(starter|growth|enterprise)$")
    admin_email: EmailStr
    admin_name: str | None = None
    trial: bool = True


@router.post("/tenants", status_code=201)
async def create_tenant(body: TenantIn, db: TenantDb = Depends(platform_db)):
    """Create a workspace and invite its first admin."""
    return await _open_workspace(db, body)


async def _open_workspace(db: TenantDb, body: TenantIn) -> dict:
    tenant = await db.one(
        """insert into tenants (name, legal_name, ein, state, plan, status, trial_ends_on)
           values (:n, :ln, :ein, :s, :plan, 'onboarding', :trial) returning *""",
        {"n": body.name.strip(), "ln": body.legal_name, "ein": body.ein, "s": body.state.upper() if body.state else None,
         "plan": body.plan, "trial": date.today() + timedelta(days=TRIAL_DAYS) if body.trial else None})

    # Step into the new tenant to create its first admin and default reminder rules.
    await db.run("select mytrakin.begin_request(:u, :t, 'system', null, null, :ip, :ua)",
                 {"u": db.ctx.user_id, "t": tenant["id"], "ip": db.ctx.ip, "ua": db.ctx.user_agent})
    existing = await db.val("select id from profiles where email = :e", {"e": body.admin_email})
    await db.run(
        """insert into memberships (tenant_id, user_id, invited_email, role, title, status)
           values (:t, :u, :e, 'tenant_admin', 'Administrator', :status)""",
        {"t": tenant["id"], "u": existing, "e": None if existing else body.admin_email,
         "status": "active" if existing else "invited"})
    await db.run("select mytrakin.seed_tenant_defaults(:t)", {"t": tenant["id"]})
    login = f"{get_settings().web_origin.rstrip('/')}/login?email={body.admin_email}"
    await send_email(db, to=body.admin_email, subject=f"Your myTrakIn workspace for {body.name} is ready", kind="welcome",
                     tenant_id=tenant["id"],
                     html_body=render(f"Welcome to myTrakIn, {body.admin_name or 'admin'}",
                                      [f"The workspace for {body.name} is ready and you are its administrator.",
                                       "Sign in with this e-mail address. The setup checklist walks you through company "
                                       "details, users, clients and vendors, contracts and your first import."],
                                      button=("Open myTrakIn", login)))
    await db.run("select mytrakin.begin_request(:u, null, 'platform_admin', null, null, :ip, :ua)",
                 {"u": db.ctx.user_id, "ip": db.ctx.ip, "ua": db.ctx.user_agent})
    return tenant


class TenantPatch(BaseModel):
    plan: str | None = Field(None, pattern="^(starter|growth|enterprise)$")
    status: str | None = Field(None, pattern="^(onboarding|active|suspended|closed)$")
    trial_ends_on: date | None = None


@router.patch("/tenants/{tenant_id}")
async def update_tenant(tenant_id: UUID, body: TenantPatch, db: TenantDb = Depends(platform_db)):
    """Change plan, extend a trial, suspend (users can't sign in) or close a workspace."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise bad_request("Nothing to change")
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    row = await db.one(f"update tenants set {sets} where id = :id returning *", {**fields, "id": tenant_id})
    if row is None:
        raise not_found("Tenant")
    return row


# ---------------------------------------------------------------------------- sign-ups
@router.get("/signups")
async def signups(db: TenantDb = Depends(platform_db), status: str | None = None):
    return await db.all(
        """select * from tenant_signups where (cast(:s as text) is null or status = :s)
            order by status <> 'pending', created_at desc""", {"s": status})


class SignupDecision(BaseModel):
    decision: str = Field(pattern="^(approved|rejected|needs_info)$")
    note: str | None = Field(None, max_length=1000)
    plan: str | None = Field(None, pattern="^(starter|growth|enterprise)$")


@router.post("/signups/{signup_id}/decision")
async def decide_signup(signup_id: UUID, body: SignupDecision, db: TenantDb = Depends(platform_db)):
    signup = await db.one("select * from tenant_signups where id = :id for update", {"id": signup_id})
    if signup is None:
        raise not_found("Sign-up")
    if signup["status"] in ("approved", "rejected"):
        raise conflict(f"This sign-up was already {signup['status']}")
    if body.decision != "approved" and not body.note:
        raise bad_request("Add a note so the company knows why")

    tenant = None
    if body.decision == "approved":
        tenant = await _open_workspace(db, TenantIn(
            name=signup["company"], ein=signup["ein"], state=signup["state"], plan=body.plan or signup["plan"],
            admin_email=signup["email"], admin_name=signup["contact_name"]))
    else:
        await send_email(None, to=signup["email"], subject="Your myTrakIn request", kind="signup",
                         html_body=render("About your myTrakIn request", [
                             "We need a little more information before we can open your workspace:" if body.decision == "needs_info"
                             else "We're not able to open a workspace for this request.", body.note or ""]))
    await db.run("update tenant_signups set status = :s, decided_by = :u, decided_at = now(), tenant_id = :t where id = :id",
                 {"s": body.decision, "u": db.ctx.user_id, "t": tenant["id"] if tenant else None, "id": signup_id})
    return {"id": signup_id, "status": body.decision, "tenant_id": tenant["id"] if tenant else None}
