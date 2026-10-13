"""Clients, prime vendors, vendors and end clients."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field

from ..deps import TenantDb, tenant_db
from ..errors import not_found

router = APIRouter(prefix="/companies", tags=["companies"])

KINDS = "^(client|prime_vendor|vendor|end_client)$"


class CompanyIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    kind: str = Field(pattern=KINDS)
    ein: str | None = Field(None, max_length=20)
    state: str | None = Field(None, max_length=2)
    address: str | None = None
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    default_terms: str = "Net 30"
    notes: str | None = None


class CompanyPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    kind: str | None = Field(None, pattern=KINDS)
    ein: str | None = None
    state: str | None = Field(None, max_length=2)
    address: str | None = None
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    default_terms: str | None = None
    notes: str | None = None
    onboarding_stage: int | None = Field(None, ge=0, le=8)


class StatusChange(BaseModel):
    status: str = Field(pattern="^(active|inactive)$")
    reason: str | None = Field(None, max_length=300)
    since: date | None = None


@router.get("")
async def list_companies(db: TenantDb = Depends(tenant_db), kind: str | None = None, status: str | None = None):
    show_money = db.ctx.allows("finance")
    rows = await db.all(
        """select c.id, c.name, c.kind, c.state, c.status, c.contact_name, c.contact_email, c.default_terms,
                  c.onboarding_stage, c.inactive_since, c.inactive_reason, c.ein,
                  (select string_agg(a.code, ', ' order by a.code) from agreements a where a.company_id = c.id and a.status = 'active') as agreements,
                  (select min(a.expires_on) from agreements a where a.company_id = c.id and a.status = 'active') as next_expiry,
                  (select coalesce(sum(balance), 0) from invoice_balances b where b.company_id = c.id and b.direction = 'ar' and b.balance > 0) as open_ar,
                  (select coalesce(sum(balance), 0) from invoice_balances b where b.company_id = c.id and b.direction = 'ap' and b.balance > 0) as open_ap,
                  (select count(*) from consultants k where k.employer_company_id = c.id and k.status = 'active') as consultants
             from companies c
            where (cast(:kind as text) is null or c.kind = :kind)
              and (cast(:status as text) is null or c.status = :status)
            order by c.status = 'inactive', c.name""",
        {"kind": kind, "status": status},
    )
    if not show_money:
        for r in rows:
            r.pop("open_ar", None)
            r.pop("open_ap", None)
            r["ein"] = None
    return rows


@router.post("", status_code=201)
async def create_company(body: CompanyIn, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("account_manager", "finance", "legal")
    return await db.one(
        """insert into companies (tenant_id, name, kind, ein, state, address, contact_name, contact_email, contact_phone,
                                  default_terms, notes, status, onboarding_stage)
           values (:t, :name, :kind, :ein, upper(:state), :address, :cn, :ce, :cp, :terms, :notes, 'onboarding', 1)
           returning *""",
        {"t": db.ctx.tenant_id, "name": body.name.strip(), "kind": body.kind, "ein": body.ein, "state": body.state,
         "address": body.address, "cn": body.contact_name, "ce": body.contact_email, "cp": body.contact_phone,
         "terms": body.default_terms, "notes": body.notes},
    )


@router.get("/{company_id}")
async def get_company(company_id: UUID, db: TenantDb = Depends(tenant_db)):
    company = await db.one("select * from companies where id = :id", {"id": company_id})
    if company is None:
        raise not_found("Company")
    if not db.ctx.allows("finance"):
        company["ein"] = None
    company["agreements"] = await db.all(
        "select id, code, kind, effective_on, expires_on, payment_terms, status, source from agreements where company_id = :id order by expires_on",
        {"id": company_id})
    company["sows"] = await db.all(
        "select s.id, s.code, s.title, s.side, s.start_date, s.end_date, b.burn_pct from sows s left join sow_burn b on b.sow_id = s.id "
        "where s.company_id = :id order by s.end_date", {"id": company_id})
    company["documents"] = await db.all(
        "select id, label, doc_type, expires_on, status, blocks from tracked_documents where company_id = :id and active", {"id": company_id})
    company["files"] = await db.all(
        "select id, name, size_bytes, mime_type, created_at from documents where owner_type = 'company' and owner_id = :id "
        "and deleted_at is null order by created_at desc", {"id": company_id})
    if db.ctx.allows("finance"):
        company["balances"] = await db.one(
            """select coalesce(sum(balance) filter (where direction = 'ar' and balance > 0), 0) as open_ar,
                      coalesce(sum(balance) filter (where direction = 'ap' and balance > 0), 0) as open_ap,
                      coalesce(sum(paid) filter (where direction = 'ap'), 0) as paid_to_them
                 from invoice_balances where company_id = :id""", {"id": company_id})
    return company


@router.patch("/{company_id}")
async def update_company(company_id: UUID, body: CompanyPatch, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("account_manager", "finance", "legal")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return await get_company(company_id, db)
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    row = await db.one(f"update companies set {sets} where id = :id returning *", {**fields, "id": company_id})
    if row is None:
        raise not_found("Company")
    return row


@router.post("/{company_id}/status")
async def change_status(company_id: UUID, body: StatusChange, db: TenantDb = Depends(tenant_db)):
    """Mark a client or vendor inactive (history is kept) or reactivate it."""
    db.ctx.require("account_manager", "finance", "legal")
    inactive = body.status == "inactive"
    row = await db.one(
        """update companies set status = :s, inactive_since = case when :inactive then coalesce(:since, current_date) end,
                  inactive_reason = case when :inactive then :reason end
            where id = :id returning id, name, status, inactive_since, inactive_reason""",
        {"s": body.status, "inactive": inactive, "since": body.since, "reason": body.reason, "id": company_id},
    )
    if row is None:
        raise not_found("Company")
    return row
