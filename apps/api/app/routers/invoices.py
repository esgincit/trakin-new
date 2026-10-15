"""Invoices both ways and the payments against them.

AR = the tenant bills its customer.  AP = a vendor or 1099 contractor bills the tenant.
Only the tenant's own two links are ever tracked — never other layers of the chain."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..deps import TenantDb, tenant_db
from ..errors import ApiError, bad_request, not_found
from ..services import workflow
from ..services.email import render, send_email
from ..services.invoicing import check_payable, generate_invoices, next_invoice_number, record_payment, settle
from ..utils import money, parse_terms_days

router = APIRouter(tags=["invoices"])


class GenerateIn(BaseModel):
    period_start: date
    period_end: date
    issue_on: date | None = None


class ManualInvoiceIn(BaseModel):
    placement_id: UUID
    period_start: date
    period_end: date
    hours: Decimal = Field(gt=0, le=1000)
    po_number: str | None = None
    memo: str | None = Field(None, max_length=500)
    send: bool = True


class VendorInvoiceIn(BaseModel):
    number: str = Field(min_length=2, max_length=40)
    placement_id: UUID
    period_start: date
    period_end: date
    hours: Decimal = Field(gt=0, le=1000)


class PaymentIn(BaseModel):
    amount: Decimal = Field(gt=0)
    paid_on: date
    method: str = Field(pattern="^(ACH|Wire|Check|Card|Other)$")
    reference: str | None = Field(None, max_length=80)
    status: str = Field("completed", pattern="^(pending|processing|completed)$")   # WF-09: in flight or done


class PaymentStatusIn(BaseModel):
    status: str = Field(pattern="^(processing|completed)$")


class NoteIn(BaseModel):
    body: str = Field(min_length=2, max_length=2000)


class RunIn(BaseModel):
    invoice_ids: list[UUID] = Field(min_length=1, max_length=200)
    method: str = Field("ACH", pattern="^(ACH|Wire|Check)$")
    paid_on: date | None = None


def _hide(row: dict, ctx) -> dict:
    """Account managers see AR money only; vendors only their own AP."""
    if row["direction"] == "ap" and not (ctx.allows("finance") or ctx.role == "vendor_admin"):
        for k in ("amount", "rate", "paid", "balance"):
            row[k] = None
    return row


_LIST_SQL = """
select b.id, b.number, b.direction, b.period_start, b.period_end, b.hours, b.approved_hours, b.rate, b.amount, b.paid,
       b.balance, b.issued_on, b.due_on, b.scheduled_on, b.terms, b.live_status, b.days_late, b.status, b.po_number,
       b.pay_when_paid_of, coalesce(co.name, k.full_name) as party, s.code as sow, cons.full_name as consultant,
       pr.name as project
  from invoice_balances b
  left join companies co on co.id = b.company_id
  left join consultants k on k.id = b.consultant_id
  left join sows s on s.id = b.sow_id
  left join placements p on p.id = b.placement_id
  left join consultants cons on cons.id = p.consultant_id
  left join projects pr on pr.id = p.project_id
"""


@router.get("/invoices")
async def list_invoices(db: TenantDb = Depends(tenant_db), direction: str = Query(..., pattern="^(ar|ap)$"),
                        status: str | None = None):
    if db.ctx.role == "consultant":
        raise ApiError(403, "forbidden", "Consultants see payment progress under My payments")
    rows = await db.all(_LIST_SQL + """ where b.direction = :d and b.status <> 'void'
                         and (cast(:s as text) is null or b.live_status = :s or (:s = 'open' and b.balance > 0))
                         order by (b.balance > 0) desc, b.due_on nulls last, b.number""",
                        {"d": direction, "s": status})
    return [_hide(r, db.ctx) for r in rows]


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: UUID, db: TenantDb = Depends(tenant_db)):
    row = await db.one(_LIST_SQL + " where b.id = :id", {"id": invoice_id})
    if row is None:
        raise not_found("Invoice")
    row["payments"] = await db.all("select id, amount, paid_on, method, reference, status, confirmed_by_name, confirmed_at from payments where invoice_id = :id order by paid_on",
                                   {"id": invoice_id})
    if db.ctx.internal:
        row["notes"] = await db.all("select body, author_name, created_at from collection_notes where invoice_id = :id order by created_at",
                                    {"id": invoice_id})
    if row["direction"] == "ap":
        upstream = await db.one("select number, hours, due_on, live_status from invoice_balances where id = :id",
                                {"id": row["pay_when_paid_of"]}) if row["pay_when_paid_of"] else None
        billed = await db.val(
            """select coalesce(sum(hours), 0) from invoices where direction = 'ar' and placement_id = (select placement_id from invoices where id = :id)
                and period_start = :ps and status <> 'void'""", {"id": invoice_id, "ps": row["period_start"]})
        row["match"] = {
            "invoiced_hours": row["hours"],
            "approved_hours": row["approved_hours"],
            # Vendors never learn what the client was billed.
            "billed_to_customer_hours": None if db.ctx.role == "vendor_admin" else billed,
            "matches": row["approved_hours"] is not None and Decimal(row["hours"]) == Decimal(row["approved_hours"]),
        }
        row["waits_for"] = None if db.ctx.role == "vendor_admin" else upstream
    return _hide(row, db.ctx)


@router.post("/invoices/generate")
async def generate(body: GenerateIn, db: TenantDb = Depends(tenant_db)):
    """Create draft AR invoices (and matching AP payables) from approved timesheets."""
    db.ctx.require("finance")
    created, blocked = await generate_invoices(db, tenant_id=db.ctx.tenant_id, user_id=db.ctx.user_id,
                                               period_start=body.period_start, period_end=body.period_end,
                                               issue_on=body.issue_on)
    return {"created": created, "blocked": blocked}


@router.post("/invoices", status_code=201)
async def create_invoice(body: ManualInvoiceIn, db: TenantDb = Depends(tenant_db)):
    """Create a client invoice by hand. Rate comes from the placement, terms from its AR settings."""
    db.ctx.require("finance")
    p = await db.one("""select p.*, c.name as customer, c.contact_email from placements p
                         left join companies c on c.id = p.ar_company_id where p.id = :id""", {"id": body.placement_id})
    if p is None:
        raise not_found("Placement")
    if p["bill_rate"] is None or p["ar_company_id"] is None:
        raise bad_request("This placement has no AR customer or bill rate")
    if (await workflow.rules(db))["requireMSA"] and not await workflow.has_active_agreement(
            db, kinds=workflow.MASTER_KINDS, company_id=p["ar_company_id"], on=body.period_end):
        raise workflow.blocked("msa_required", f"{p['customer']} has no active MSA — invoices are blocked until one is signed")
    issued = date.today()
    invoice = await db.one(
        """insert into invoices (tenant_id, number, direction, placement_id, company_id, sow_id, period_start, period_end, hours,
                                 rate, amount, issued_on, due_on, terms, status, po_number, memo, created_by)
           values (:t, :n, 'ar', :pl, :co, :sow, :ps, :pe, :h, :r, :a, :iss, :due, :terms, :st, :po, :memo, :u)
           returning id, number, amount, due_on""",
        {"t": db.ctx.tenant_id, "n": await next_invoice_number(db, db.ctx.tenant_id, "AR"), "pl": p["id"], "co": p["ar_company_id"],
         "sow": p["ar_sow_id"], "ps": body.period_start, "pe": body.period_end, "h": body.hours, "r": p["bill_rate"],
         "a": money(body.hours * p["bill_rate"]), "iss": issued, "due": issued + timedelta(days=parse_terms_days(p["ar_terms"])),
         "terms": p["ar_terms"], "st": "sent" if body.send else "draft", "po": body.po_number, "memo": body.memo, "u": db.ctx.user_id})
    if body.send and p["contact_email"]:
        await send_email(db, to=p["contact_email"], subject=f"Invoice {invoice['number']}",
                         html_body=render(f"Invoice {invoice['number']}",
                                          [f"Amount due: ${invoice['amount']:,.2f}", f"Due date: {invoice['due_on']:%b %d, %Y}",
                                           "Reply to this e-mail with any questions about the hours or the amount."]),
                         kind="invoice", tenant_id=db.ctx.tenant_id, ref_type="invoice", ref_id=invoice["id"])
    return invoice


@router.post("/invoices/{invoice_id}/send")
async def send_invoice(invoice_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Send a draft client invoice: it is dated today and e-mailed to the customer's contact."""
    db.ctx.require("finance")
    inv = await db.one(
        """update invoices i set status = 'sent', issued_on = current_date
            where i.id = :id and i.status = 'draft' and i.direction = 'ar'
        returning i.id, i.number, i.amount, i.due_on, i.company_id""", {"id": invoice_id})
    if inv is None:
        raise ApiError(409, "not_draft", "Only draft client invoices can be sent")
    contact = await db.val("select contact_email from companies where id = :c", {"c": inv["company_id"]})
    if contact:
        tenant = await db.val("select name from tenants where id = :t", {"t": db.ctx.tenant_id})
        await send_email(db, to=contact, subject=f"Invoice {inv['number']} from {tenant}", kind="invoice",
                         tenant_id=db.ctx.tenant_id, ref_type="invoice", ref_id=inv["id"],
                         html_body=render(f"Invoice {inv['number']}",
                                          [f"Amount due: ${inv['amount']:,.2f}",
                                           f"Due date: {inv['due_on']:%b %d, %Y}" if inv["due_on"] else "Due on receipt",
                                           "Reply to this e-mail with any questions about the hours or the amount."]))
    return {"id": invoice_id, "status": "sent", "emailed": bool(contact)}


@router.post("/vendor-invoices", status_code=201)
async def submit_vendor_invoice(body: VendorInvoiceIn, db: TenantDb = Depends(tenant_db)):
    """A vendor submits its invoice. It is matched against approved timesheets automatically."""
    if db.ctx.role != "vendor_admin":
        raise ApiError(403, "forbidden", "Vendor portal only")
    p = await db.one("select * from placements where id = :id and ap_company_id = :co", {"id": body.placement_id, "co": db.ctx.company_id})
    if p is None:
        raise not_found("Placement")
    approved = await db.val(
        """select coalesce(sum(e.hours), 0) from timesheet_entries e join timesheets t on t.id = e.timesheet_id
            where e.placement_id = :p and t.status = 'approved' and e.work_date between :s and :e""",
        {"p": p["id"], "s": body.period_start, "e": body.period_end})
    ar = await db.val("""select id from invoices where direction = 'ar' and placement_id = :p and period_start = :s and status <> 'void'""",
                      {"p": p["id"], "s": body.period_start}) if p["pay_when_paid"] else None
    status = "received" if Decimal(approved) == body.hours else "exception"
    return await db.one(
        """insert into invoices (tenant_id, number, direction, placement_id, company_id, sow_id, period_start, period_end, hours,
                                 approved_hours, rate, amount, issued_on, due_on, terms, pay_when_paid_of, status)
           values (:t, :n, 'ap', :pl, :co, :sow, :ps, :pe, :h, :ah, :r, :a, current_date, :due, :terms, :ar, :st)
           returning id, number, amount, status""",
        {"t": db.ctx.tenant_id, "n": body.number, "pl": p["id"], "co": db.ctx.company_id, "sow": p["ap_sow_id"],
         "ps": body.period_start, "pe": body.period_end, "h": body.hours, "ah": approved, "r": p["pay_rate"],
         "a": money(body.hours * (p["pay_rate"] or 0)), "due": None if p["pay_when_paid"] else date.today() + timedelta(days=parse_terms_days(p["ap_terms"])),
         "terms": p["ap_terms"], "ar": ar, "st": status})


@router.post("/invoices/{invoice_id}/payments", status_code=201)
async def add_payment(invoice_id: UUID, body: PaymentIn, db: TenantDb = Depends(tenant_db)):
    """Record money received from a customer or paid to a vendor. Paying an AR invoice in full
    releases any pay-when-paid vendor invoices waiting on it."""
    db.ctx.require("finance")
    if body.paid_on > date.today():
        raise bad_request("The payment date can't be in the future")
    return await record_payment(db, tenant_id=db.ctx.tenant_id, user_id=db.ctx.user_id, invoice_id=invoice_id,
                                amount=body.amount, paid_on=body.paid_on, method=body.method, reference=body.reference,
                                status=body.status)


# ----------------------------------------------------------------------------- payment lifecycle (WF-09)
@router.post("/payments/{payment_id}/status")
async def advance_payment(payment_id: UUID, body: PaymentStatusIn, db: TenantDb = Depends(tenant_db)):
    """Move a payment in flight forward: pending → processing → completed. Completed counts against the invoice."""
    db.ctx.require("finance")
    order = ["pending", "processing", "completed"]
    current = await db.one("select invoice_id, status, amount from payments where id = :id for update", {"id": payment_id})
    if current is None:
        raise not_found("Payment")
    if current["status"] not in order or order.index(body.status) <= order.index(current["status"]):
        raise ApiError(409, "bad_transition", f"A {current['status']} payment can't move to {body.status}")
    if body.status == "completed":
        # The same rules as recording a payment: not void, not on hold, payee agreement, no overpayment.
        await check_payable(db, current["invoice_id"], current["amount"], date.today(), exclude_payment=payment_id)
    await db.run("update payments set status = :s where id = :id", {"s": body.status, "id": payment_id})
    result = {"id": payment_id, "status": body.status}
    if body.status == "completed":
        result |= await settle(db, current["invoice_id"])
    return result


@router.post("/payments/{payment_id}/confirm")
async def confirm_payment(payment_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Payment confirmation closes the financial lifecycle: finance confirms money received from a customer;
    the vendor (or 1099 contractor) — or finance on their behalf — confirms money paid to them."""
    payment = await db.one(
        """select p.id, p.status, i.direction, i.company_id, i.consultant_id from payments p
             join invoices i on i.id = p.invoice_id where p.id = :id""", {"id": payment_id})
    if payment is None:
        raise not_found("Payment")
    payee = payment["direction"] == "ap" and (
        (db.ctx.role == "vendor_admin" and payment["company_id"] == db.ctx.company_id)
        or (db.ctx.role == "consultant" and payment["consultant_id"] == db.ctx.consultant_id))
    if not (db.ctx.allows("finance") or payee):
        raise ApiError(403, "forbidden", "Only finance or the payee can confirm this payment")
    if payment["status"] != "completed":
        raise ApiError(409, "not_completed", "Only a completed payment can be confirmed"
                       + (" — it is already confirmed" if payment["status"] == "confirmed" else ""))
    name = await db.val("select full_name from profiles where id = :u", {"u": db.ctx.user_id}) or db.ctx.email
    return await db.one(
        """update payments set status = 'confirmed', confirmed_by = :u, confirmed_by_name = :n, confirmed_at = now()
            where id = :id and status = 'completed'
        returning id, status, confirmed_by_name, confirmed_at""",
        {"u": db.ctx.user_id, "n": name, "id": payment_id})


@router.post("/invoices/{invoice_id}/notes", status_code=201)
async def add_note(invoice_id: UUID, body: NoteIn, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("finance", "account_manager")
    name = await db.val("select coalesce(full_name, email::text) from profiles where id = :u", {"u": db.ctx.user_id})
    return await db.one(
        "insert into collection_notes (tenant_id, invoice_id, body, author_id, author_name) values (:t, :i, :b, :u, :n) returning *",
        {"t": db.ctx.tenant_id, "i": invoice_id, "b": body.body, "u": db.ctx.user_id, "n": name})


@router.post("/invoices/{invoice_id}/resolve")
async def resolve_exception(invoice_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Accept a vendor invoice at the approved hours (amount is recalculated)."""
    db.ctx.require("finance")
    row = await db.one(
        """update invoices set hours = approved_hours, amount = round(approved_hours * rate, 2), status = 'received'
            where id = :id and direction = 'ap' and status = 'exception' and approved_hours is not null
            returning id, number, hours, amount""", {"id": invoice_id})
    if row is None:
        raise ApiError(409, "not_exception", "This invoice isn't waiting on a mismatch")
    return row


@router.post("/invoices/{invoice_id}/void")
async def void_invoice(invoice_id: UUID, body: NoteIn, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("finance")
    if await db.val("select count(*) from payments where invoice_id = :id", {"id": invoice_id}):
        raise ApiError(409, "has_payments", "Invoices with payments can't be voided — issue a credit instead")
    if await db.run("update invoices set status = 'void', memo = coalesce(memo || ' | ', '') || :r where id = :id",
                    {"id": invoice_id, "r": f"Voided: {body.body}"}) == 0:
        raise not_found("Invoice")
    return {"id": invoice_id, "status": "void"}


@router.post("/payment-runs")
async def payment_run(body: RunIn, db: TenantDb = Depends(tenant_db)):
    """Pay several vendor / 1099 invoices at once. Held or mismatched invoices are skipped."""
    db.ctx.require("finance")
    paid_on = body.paid_on or date.today()
    run_ref = f"RUN-{paid_on:%Y%m%d}-{await db.val('select mytrakin.next_number(:t, :k)', {'t': db.ctx.tenant_id, 'k': 'payment_run'})}"
    paid, skipped = [], []
    for invoice_id in body.invoice_ids:
        inv = await db.one("select id, number, direction, balance, live_status from invoice_balances where id = :id", {"id": invoice_id})
        if inv is None or inv["direction"] != "ap" or inv["balance"] <= 0 or inv["live_status"] in ("held", "exception"):
            skipped.append({"id": invoice_id, "number": inv["number"] if inv else None,
                            "reason": "not payable" if inv else "not found"})
            continue
        await record_payment(db, tenant_id=db.ctx.tenant_id, user_id=db.ctx.user_id, invoice_id=invoice_id,
                             amount=inv["balance"], paid_on=paid_on, method=body.method, reference=run_ref)
        paid.append({"id": invoice_id, "number": inv["number"], "amount": inv["balance"]})
    return {"reference": run_ref, "paid": paid, "skipped": skipped, "total": sum((p["amount"] for p in paid), Decimal(0))}


@router.get("/payments")
async def ledger(db: TenantDb = Depends(tenant_db), since: date | None = Query(None, alias="from")):
    """Every payment in and out, newest first."""
    if not (db.ctx.allows("finance") or db.ctx.role == "vendor_admin"):
        raise ApiError(403, "forbidden", "Finance only")
    return await db.all(
        """select p.id, p.paid_on, case i.direction when 'ar' then 'in' else 'out' end as direction, p.amount, p.method, p.reference, p.status, p.confirmed_by_name, p.confirmed_at,
                  i.number as invoice, coalesce(co.name, k.full_name) as party
             from payments p join invoices i on i.id = p.invoice_id
             left join companies co on co.id = i.company_id left join consultants k on k.id = i.consultant_id
            where (cast(:f as date) is null or p.paid_on >= :f)
            order by p.paid_on desc, p.created_at desc limit 2000""", {"f": since})


@router.get("/payment-flow")
async def payment_flow(db: TenantDb = Depends(tenant_db), only_open: bool = True):
    """One row per placement and period: the AR card and the AP card side by side."""
    if not db.ctx.internal:
        raise ApiError(403, "forbidden", "Staff only")
    rows = await db.all(
        """select ar.id as ar_id, ar.number as ar_number, ar.period_start, ar.period_end, ar.hours, ar.amount as ar_amount,
                  ar.balance as ar_balance, ar.due_on as ar_due, ar.live_status as ar_status, cust.name as customer,
                  ec.name as end_client, c.full_name as consultant, c.engagement, pr.name as project,
                  ap.id as ap_id, ap.number as ap_number, ap.amount as ap_amount, ap.balance as ap_balance,
                  coalesce(ap.scheduled_on, ap.due_on) as ap_due, ap.live_status as ap_status, coalesce(pco.name, pk.full_name) as payee
             from invoice_balances ar
             join placements p on p.id = ar.placement_id
             join consultants c on c.id = p.consultant_id
             join projects pr on pr.id = p.project_id
             left join companies cust on cust.id = ar.company_id
             left join companies ec on ec.id = p.end_client_company_id
             left join invoice_balances ap on ap.placement_id = p.id and ap.direction = 'ap' and ap.period_start = ar.period_start and ap.status <> 'void'
             left join companies pco on pco.id = ap.company_id
             left join consultants pk on pk.id = ap.consultant_id
            where ar.direction = 'ar' and ar.status <> 'void'
              and (not :open or ar.balance > 0 or coalesce(ap.balance, 0) > 0)
            order by ar.period_start desc, c.full_name""", {"open": only_open})
    if not db.ctx.allows("finance"):
        for r in rows:
            r["ap_amount"] = r["ap_balance"] = None
    return rows
