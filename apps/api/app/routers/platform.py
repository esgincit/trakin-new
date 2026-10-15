"""Platform owner console (the company running myTrakIn as SaaS): tenants, sign-up
approvals, and revenue per user."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..deps import TenantDb, platform_db
from ..errors import bad_request, not_found

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
