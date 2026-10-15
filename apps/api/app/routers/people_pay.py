"""Paying people outside the vendor chain: W-2 payroll records, referral fees, the 1099 year-end
summary, and approving consultants' expenses and time off.

Payroll itself runs in your payroll provider (ADP, Gusto, Paychex ...). myTrakIn keeps the
results (imported or entered) so margins and cash flow are complete.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator

from ..deps import TenantDb, tenant_db
from ..errors import bad_request, conflict, not_found
from ..utils import money

router = APIRouter(tags=["payroll, 1099 & referrals"])


# ============================================================================ W-2 payroll
class PayrollIn(BaseModel):
    consultant_id: UUID
    period_start: date
    period_end: date
    pay_date: date
    hours: Decimal | None = Field(None, ge=0)
    gross: Decimal = Field(gt=0)
    employer_taxes: Decimal = Field(Decimal(0), ge=0)
    benefits: Decimal = Field(Decimal(0), ge=0)
    net: Decimal | None = Field(None, ge=0)


@router.get("/payroll")
async def payroll(db: TenantDb = Depends(tenant_db), since: date | None = Query(None, alias="from"),
                  until: date | None = Query(None, alias="to")):
    db.ctx.require("finance")
    return await db.all(
        """select pl.*, c.full_name, c.engagement, (pl.gross + pl.employer_taxes + pl.benefits) as total_cost
             from payroll_lines pl join consultants c on c.id = pl.consultant_id
            where (cast(:f as date) is null or pl.pay_date >= :f) and (cast(:u as date) is null or pl.pay_date <= :u)
            order by pl.pay_date desc, c.full_name""", {"f": since, "u": until})


@router.post("/payroll", status_code=201)
async def add_payroll(body: PayrollIn, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("finance")
    engagement = await db.val("select engagement from consultants where id = :id", {"id": body.consultant_id})
    if engagement is None:
        raise not_found("Employee")
    if not engagement.startswith("w2"):
        raise bad_request("Payroll is for W-2 employees. Pay C2C vendors and 1099 contractors through AP invoices.")
    return await db.one(
        """insert into payroll_lines (tenant_id, consultant_id, period_start, period_end, pay_date, hours, gross, employer_taxes,
                                      benefits, net, source)
           values (:t, :c, :ps, :pe, :pd, :h, :g, :tax, :ben, :net, 'manual') returning *""",
        {"t": db.ctx.tenant_id, "c": body.consultant_id, "ps": body.period_start, "pe": body.period_end, "pd": body.pay_date,
         "h": body.hours, "g": body.gross, "tax": body.employer_taxes, "ben": body.benefits, "net": body.net})


@router.get("/payroll/margin")
async def w2_margin(db: TenantDb = Depends(tenant_db), since: date = Query(alias="from"), until: date = Query(alias="to")):
    """Billed (AR) versus fully loaded payroll cost per W-2 employee for a period."""
    db.ctx.require("finance")
    return await db.all(
        """select c.id, c.full_name, c.engagement,
                  coalesce((select sum(i.amount) from invoices i join placements p on p.id = i.placement_id
                             where p.consultant_id = c.id and i.direction = 'ar' and i.status <> 'void'
                               and i.period_start between :f and :u), 0) as billed,
                  coalesce((select sum(pl.gross + pl.employer_taxes + pl.benefits) from payroll_lines pl
                             where pl.consultant_id = c.id and pl.period_start between :f and :u), 0) as payroll_cost
             from consultants c where c.engagement like 'w2%' and c.status <> 'onboarding'
            order by c.full_name""", {"f": since, "u": until})


# ============================================================================ referrals
class ReferralIn(BaseModel):
    referrer_name: str = Field(min_length=2, max_length=160)
    referrer_type: str = Field(pattern="^(individual_1099|company|employee)$")
    consultant_id: UUID
    basis: str = Field(pattern="^(hourly|one_time)$")
    rate_per_hour: Decimal | None = Field(None, gt=0)
    hour_cap: Decimal | None = Field(None, gt=0)
    one_time_amount: Decimal | None = Field(None, gt=0)
    eligible_on: date | None = None
    w9_on_file: bool = False

    @model_validator(mode="after")
    def _terms(self):
        if self.basis == "hourly" and not self.rate_per_hour:
            raise ValueError("Hourly referral fees need a rate per hour")
        if self.basis == "one_time" and not self.one_time_amount:
            raise ValueError("One-time referral fees need an amount")
        return self


class ReferralPaymentIn(BaseModel):
    amount: Decimal = Field(gt=0)
    paid_on: date
    reference: str | None = Field(None, max_length=80)


_REFERRALS_SQL = """
select r.*, c.full_name as consultant,
       coalesce((select sum(e.hours) from timesheet_entries e join timesheets t on t.id = e.timesheet_id
                   join placements p on p.id = e.placement_id
                  where p.consultant_id = r.consultant_id and t.status = 'approved'
                    and e.work_date >= coalesce(r.eligible_on, '1900-01-01')), 0) as approved_hours,
       coalesce((select sum(rp.amount) from referral_payments rp where rp.agreement_id = r.id), 0) as paid
  from referral_agreements r join consultants c on c.id = r.consultant_id
"""


def _earned(r: dict) -> dict:
    """Hourly: approved hours since eligibility × rate, up to the hour cap. One-time: due once eligible."""
    if r["basis"] == "hourly":
        hours = Decimal(r["approved_hours"])
        if r["hour_cap"] is not None:
            hours = min(hours, Decimal(r["hour_cap"]))
        r["earned"] = money(hours * Decimal(r["rate_per_hour"] or 0))
        r["hours_counted"] = hours
    else:
        due = r["eligible_on"] is None or r["eligible_on"] <= date.today()
        r["earned"] = money(r["one_time_amount"] if due else 0)
    r["balance"] = money(Decimal(r["earned"]) - Decimal(r["paid"]))
    r["needs_w9"] = r["referrer_type"] == "individual_1099" and not r["w9_on_file"]
    return r


@router.get("/referrals")
async def referrals(db: TenantDb = Depends(tenant_db)):
    db.ctx.require("finance", "hr")
    return [_earned(r) for r in await db.all(_REFERRALS_SQL + " order by r.created_at desc")]


@router.post("/referrals", status_code=201)
async def add_referral(body: ReferralIn, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("finance", "hr")
    row = await db.one(
        """insert into referral_agreements (tenant_id, referrer_name, referrer_type, consultant_id, basis, rate_per_hour, hour_cap,
                                            one_time_amount, eligible_on, w9_on_file)
           values (:t, :n, :rt, :c, :b, :rate, :cap, :once, :elig, :w9) returning id""",
        {"t": db.ctx.tenant_id, "n": body.referrer_name.strip(), "rt": body.referrer_type, "c": body.consultant_id, "b": body.basis,
         "rate": body.rate_per_hour, "cap": body.hour_cap, "once": body.one_time_amount, "elig": body.eligible_on, "w9": body.w9_on_file})
    return _earned(await db.one(_REFERRALS_SQL + " where r.id = :id", {"id": row["id"]}))


@router.post("/referrals/{agreement_id}/payments", status_code=201)
async def pay_referral(agreement_id: UUID, body: ReferralPaymentIn, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("finance")
    r = await db.one(_REFERRALS_SQL + " where r.id = :id", {"id": agreement_id})
    if r is None:
        raise not_found("Referral agreement")
    r = _earned(r)
    if r["needs_w9"]:
        raise conflict("Collect a W-9 from this referrer before paying (needed for the 1099).", "w9_missing")
    if body.amount > r["balance"]:
        raise bad_request(f"Only ${r['balance']:,.2f} is earned and unpaid")
    await db.run("insert into referral_payments (tenant_id, agreement_id, amount, paid_on, reference) values (:t, :a, :amt, :d, :ref)",
                 {"t": db.ctx.tenant_id, "a": agreement_id, "amt": body.amount, "d": body.paid_on, "ref": body.reference})
    return _earned(await db.one(_REFERRALS_SQL + " where r.id = :id", {"id": agreement_id}))


@router.patch("/referrals/{agreement_id}")
async def update_referral(agreement_id: UUID, w9_on_file: bool, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("finance", "hr")
    if await db.run("update referral_agreements set w9_on_file = :w where id = :id", {"w": w9_on_file, "id": agreement_id}) == 0:
        raise not_found("Referral agreement")
    return {"id": agreement_id, "w9_on_file": w9_on_file}


# ============================================================================ 1099 summary
def default_threshold(year: int) -> Decimal:
    # 1099-NEC reporting threshold: $600 through tax year 2025; $2,000 from 2026 (indexed later).
    # Confirm with your tax advisor each year; the screen lets you override it.
    return Decimal(600) if year <= 2025 else Decimal(2000)


@router.get("/form-1099")
async def form_1099(db: TenantDb = Depends(tenant_db), year: int = Query(ge=2000, le=2100),
                    threshold: Decimal | None = Query(None, ge=0)):
    """Everything paid to 1099 contractors and individual referrers in a calendar year (cash basis)."""
    db.ctx.require("finance")
    limit = threshold if threshold is not None else default_threshold(year)
    contractors = await db.all(
        """select 'contractor' as kind, k.id, k.full_name as payee, k.email,
                  sum(p.amount) as paid, count(distinct i.id) as invoices,
                  exists (select 1 from tracked_documents d where d.consultant_id = k.id and d.doc_type = 'w9' and d.status = 'valid') as w9_on_file
             from payments p join invoices i on i.id = p.invoice_id join consultants k on k.id = i.consultant_id
            where i.direction = 'ap' and extract(year from p.paid_on) = :y and p.status in ('completed', 'confirmed')
            group by k.id""", {"y": year})
    referrers = await db.all(
        """select 'referral' as kind, null as id, r.referrer_name as payee, null as email, sum(rp.amount) as paid,
                  count(*) as invoices, bool_or(r.w9_on_file) as w9_on_file
             from referral_payments rp join referral_agreements r on r.id = rp.agreement_id
            where r.referrer_type = 'individual_1099' and extract(year from rp.paid_on) = :y
            group by r.referrer_name""", {"y": year})
    rows = sorted(contractors + referrers, key=lambda r: r["paid"], reverse=True)
    for r in rows:
        r["reportable"] = Decimal(r["paid"]) >= limit
    return {"year": year, "threshold": limit, "rows": rows,
            "note": "Cash basis: payments made in the calendar year. Corporations (C2C vendors) are generally not reported. "
                    "File 1099-NEC by January 31. Confirm thresholds and exceptions with your tax advisor."}


# ============================================================================ expenses & time off (staff side)
class Decision(BaseModel):
    decision: str
    note: str | None = Field(None, max_length=300)


@router.get("/expenses")
async def expenses(db: TenantDb = Depends(tenant_db), status: str | None = None):
    db.ctx.require("finance", "hr", "approver")
    return await db.all(
        """select e.*, c.full_name as consultant, pr.name as project from expenses e
             join consultants c on c.id = e.consultant_id
             left join placements p on p.id = e.placement_id left join projects pr on pr.id = p.project_id
            where (cast(:s as text) is null or e.status = :s) order by e.status = 'submitted' desc, e.spent_on desc""",
        {"s": status})


@router.post("/expenses/{expense_id}/decision")
async def decide_expense(expense_id: UUID, body: Decision, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("finance", "hr", "approver")
    allowed = {"approved": ("submitted",), "rejected": ("submitted",), "reimbursed": ("approved",)}
    if body.decision not in allowed:
        raise bad_request("Decision must be approved, rejected or reimbursed")
    if body.decision == "reimbursed":
        db.ctx.require("finance")
    row = await db.one(
        "update expenses set status = :s, decided_by = :u where id = :id and status = any(:from) returning *",
        {"s": body.decision, "u": db.ctx.user_id, "id": expense_id, "from": list(allowed[body.decision])})
    if row is None:
        raise conflict("This expense isn't in a state that allows that")
    return row


@router.get("/time-off")
async def time_off(db: TenantDb = Depends(tenant_db), status: str | None = None):
    db.ctx.require("hr", "approver", "account_manager")
    return await db.all(
        """select t.*, c.full_name as consultant, (t.ends_on - t.starts_on + 1) as days from time_off t
             join consultants c on c.id = t.consultant_id
            where (cast(:s as text) is null or t.status = :s) order by t.status = 'requested' desc, t.starts_on""", {"s": status})


@router.post("/time-off/{request_id}/decision")
async def decide_time_off(request_id: UUID, body: Decision, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("hr", "approver", "account_manager")
    if body.decision not in ("approved", "declined"):
        raise bad_request("Decision must be approved or declined")
    row = await db.one("update time_off set status = :s where id = :id and status = 'requested' returning *",
                       {"s": body.decision, "id": request_id})
    if row is None:
        raise conflict("Only open requests can be decided")
    return row
