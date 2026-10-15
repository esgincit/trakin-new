"""Turning approved time into invoices, and recording payments.

Invoices are created per placement and period:
  * AR: hours x bill rate, billed to the placement's AR customer, due per AR terms.
  * AP: hours x pay rate, owed to the vendor (or 1099 contractor). With pay-when-paid
    the AP invoice points at the AR invoice and is "held" until that is paid.
W-2 placements have no AP invoice — payroll covers them.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from ..db import Db
from ..errors import bad_request, conflict, not_found
from ..utils import money, parse_terms_days
from . import numbering, workflow


async def next_invoice_number(db: Db, tenant_id: Any, prefix: str) -> str:
    """AR / AP number from the tenant's numbering template (default AR-2026-0001)."""
    return await numbering.next_code(db, f"invoice_{prefix.lower()}")


async def approved_hours_by_placement(db: Db, period_start: date, period_end: date) -> list[dict]:
    """Approved, not-yet-invoiced hours for each placement in the period."""
    return await db.all(
        """
        select p.id as placement_id, p.consultant_id, p.ar_company_id, p.ar_sow_id, p.bill_rate, p.ar_terms,
               p.ap_company_id, p.ap_consultant_id, p.ap_sow_id, p.pay_rate, p.ap_terms, p.pay_when_paid,
               sum(e.hours) as hours
          from timesheet_entries e
          join timesheets t on t.id = e.timesheet_id and t.status = 'approved'
          join placements p on p.id = e.placement_id
         where e.work_date between :start and :end
           and not exists (select 1 from invoices i
                            where i.placement_id = p.id and i.direction = 'ar' and i.status <> 'void'
                              and i.period_start <= :end and i.period_end >= :start)
         group by p.id
        having sum(e.hours) > 0
        """,
        {"start": period_start, "end": period_end},
    )


async def generate_invoices(db: Db, *, tenant_id: Any, user_id: Any, period_start: date, period_end: date,
                            issue_on: date | None = None) -> tuple[list[dict], list[str]]:
    if period_end < period_start:
        raise bad_request("The period ends before it starts")
    issue_on = issue_on or date.today()
    created: list[dict] = []
    blocked: list[str] = []
    need_msa = (await workflow.rules(db))["requireMSA"]
    for row in await approved_hours_by_placement(db, period_start, period_end):
        if row["bill_rate"] is None or row["ar_company_id"] is None:
            continue
        # AGR-09 / WF-01: no invoice to a customer without an active MSA (unless the tenant switched the rule off).
        if need_msa and not await workflow.has_active_agreement(db, kinds=workflow.MASTER_KINDS,
                                                                company_id=row["ar_company_id"], on=period_end):
            name = await db.val("select name from companies where id = :id", {"id": row["ar_company_id"]})
            blocked.append(f"{name}: no active MSA — not invoiced")
            continue
        hours = Decimal(row["hours"])
        ar_amount = money(hours * row["bill_rate"])
        ar_number = await next_invoice_number(db, tenant_id, "AR")
        ar = await db.one(
            """insert into invoices (tenant_id, number, direction, placement_id, company_id, sow_id, period_start, period_end,
                                     hours, rate, amount, issued_on, due_on, terms, status, created_by)
               values (:t, :n, 'ar', :pl, :co, :sow, :ps, :pe, :h, :r, :a, :iss, :due, :terms, 'draft', :u)
               returning id, number, amount""",
            {"t": tenant_id, "n": ar_number, "pl": row["placement_id"], "co": row["ar_company_id"], "sow": row["ar_sow_id"],
             "ps": period_start, "pe": period_end, "h": hours, "r": row["bill_rate"], "a": ar_amount, "iss": issue_on,
             "due": issue_on + timedelta(days=parse_terms_days(row["ar_terms"])), "terms": row["ar_terms"], "u": user_id},
        )
        created.append({"direction": "ar", **ar})

        payee = row["ap_company_id"] or row["ap_consultant_id"]
        if payee and row["pay_rate"] is not None:
            if need_msa and not await workflow.has_active_agreement(
                    db, kinds=workflow.MASTER_KINDS, company_id=row["ap_company_id"],
                    consultant_id=row["ap_consultant_id"], on=period_end):
                blocked.append(f"Payable for placement {row['placement_id']}: no active vendor or contractor agreement")
                continue
            ap_amount = money(hours * row["pay_rate"])
            ap = await db.one(
                """insert into invoices (tenant_id, number, direction, placement_id, company_id, consultant_id, sow_id,
                                         period_start, period_end, hours, approved_hours, rate, amount, issued_on, due_on,
                                         terms, pay_when_paid_of, status, created_by)
                   values (:t, :n, 'ap', :pl, :co, :con, :sow, :ps, :pe, :h, :h, :r, :a, :iss, :due, :terms, :pwp, 'received', :u)
                   returning id, number, amount""",
                {"t": tenant_id, "n": await next_invoice_number(db, tenant_id, "AP"), "pl": row["placement_id"],
                 "co": row["ap_company_id"], "con": row["ap_consultant_id"], "sow": row["ap_sow_id"],
                 "ps": period_start, "pe": period_end, "h": hours, "r": row["pay_rate"], "a": ap_amount, "iss": issue_on,
                 "due": None if row["pay_when_paid"] else issue_on + timedelta(days=parse_terms_days(row["ap_terms"])),
                 "terms": row["ap_terms"], "pwp": ar["id"] if row["pay_when_paid"] else None, "u": user_id},
            )
            created.append({"direction": "ap", **ap})
    return created, blocked


async def record_payment(db: Db, *, tenant_id: Any, user_id: Any, invoice_id: Any, amount: Decimal,
                         paid_on: date, method: str, reference: str | None, status: str = "completed") -> dict:
    """Record money received (AR) or paid (AP). For AR, returns AP invoices that this releases.
    status pending / processing records a payment in flight; it counts once it is completed (WF-09)."""
    amount = money(amount)
    await check_payable(db, invoice_id, amount, paid_on)
    payment_id = await db.val(
        """insert into payments (tenant_id, invoice_id, amount, paid_on, method, reference, created_by, status)
           values (:t, :i, :a, :d, :m, :r, :u, :s) returning id""",
        {"t": tenant_id, "i": invoice_id, "a": amount, "d": paid_on, "m": method, "r": reference, "u": user_id,
         "s": status},
    )
    return {"payment_id": payment_id, "invoice_id": invoice_id, "amount": amount, "status": status,
            **await settle(db, invoice_id)}


async def check_payable(db: Db, invoice_id: Any, amount: Decimal, paid_on: date, *, exclude_payment: Any = None) -> None:
    """Every rule a payment must pass — when it is recorded and again when an in-flight payment is completed.
    Locks the invoice so two people paying at once can't overpay it. Payments still in flight (pending /
    processing) count against the balance here, so in-flight payments can never add up to more than is owed."""
    if await db.one("select id from invoices where id = :id for update", {"id": invoice_id}) is None:
        raise not_found("Invoice")
    invoice = await db.one("select * from invoice_balances where id = :id", {"id": invoice_id})
    if invoice is None:
        raise not_found("Invoice")
    if invoice["status"] == "void":
        raise conflict("This invoice is void")
    if amount <= 0:
        raise bad_request("Enter an amount above zero")
    in_flight = money(await db.val(
        """select coalesce(sum(amount), 0) from payments where invoice_id = :id and status in ('pending', 'processing')
             and id is distinct from cast(:x as uuid)""", {"id": invoice_id, "x": exclude_payment}))
    open_balance = money(invoice["balance"]) - in_flight
    if amount > open_balance:
        raise bad_request(f"That is more than the open balance of ${open_balance:,.2f}"
                          + (f" (${in_flight:,.2f} is already in flight)" if in_flight else ""))
    if invoice["direction"] == "ap" and invoice["live_status"] in {"held", "exception"}:
        raise conflict("This vendor invoice is on hold — resolve it before paying")
    # Money received from a customer is always recorded; money paid out needs an active agreement with the payee.
    if invoice["direction"] == "ap" and (await workflow.rules(db))["requireMSA"] and not await workflow.has_active_agreement(
            db, kinds=workflow.MASTER_KINDS, company_id=invoice["company_id"], consultant_id=invoice["consultant_id"],
            on=paid_on):
        raise conflict("No active agreement with this payee — vendor payments are blocked until one is signed")


async def settle(db: Db, invoice_id: Any) -> dict:
    """After a payment counts (completed / confirmed): mark the invoice paid when nothing is left, and a fully
    paid AR invoice releases the pay-when-paid vendor invoices waiting on it."""
    after = await db.one("select direction, balance from invoice_balances where id = :id", {"id": invoice_id})
    balance = money(after["balance"]) if after else Decimal(0)
    released: list[dict] = []
    if after and balance <= 0:
        await db.run("update invoices set status = 'paid' where id = :id", {"id": invoice_id})
        if after["direction"] == "ar":
            released = await db.all(
                """update invoices ap set due_on = coalesce(ap.due_on, current_date + 3)
                    where ap.pay_when_paid_of = :id and ap.direction = 'ap' and ap.status not in ('paid', 'void', 'exception')
                    returning ap.id, ap.number""",
                {"id": invoice_id},
            )
    return {"balance": balance, "released": released}
