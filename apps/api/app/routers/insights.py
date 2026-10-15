"""Smart suggestions: what needs attention, ranked, each with a one-click next step.

The suggestions are computed from the data with plain rules (fast, explainable, no data
leaves the database). If an AI key is set (DeepSeek or Anthropic), /insights/ask can also
answer a question in plain English using only those suggestions — never raw records —
and only with the amounts the caller is already allowed to see.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx
import orjson
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..config import get_settings
from ..deps import TenantDb, tenant_db
from ..errors import ApiError
from ..utils import week_start

log = logging.getLogger("mytrakin.insights")
router = APIRouter(prefix="/insights", tags=["smart suggestions"])


def _s(priority: int, area: str, title: str, detail: str, action: str, link: str, amount=None) -> dict:
    return {"priority": priority, "area": area, "title": title, "detail": detail, "action": action, "link": link, "amount": amount}


@router.get("")
async def suggestions(db: TenantDb = Depends(tenant_db)) -> list[dict]:
    ctx = db.ctx
    if not ctx.internal:
        return []
    out: list[dict] = []
    last_week = week_start(date.today()) - timedelta(days=7)

    if ctx.allows("approver", "account_manager", "hr", "finance"):
        waiting = await db.val("select count(*) from timesheets where status = 'submitted'")
        if waiting:
            out.append(_s(80, "Timesheets", f"{waiting} timesheet(s) waiting for approval",
                          "Timesheets that pass every check (hours match the schedule, no overtime, dates inside the SOW) "
                          "can be approved together.", "Review & approve passing", "/timesheets?status=submitted"))
        missing = await db.all(
            """select c.full_name from consultants c
                where c.status = 'active'
                  and exists (select 1 from placements p where p.consultant_id = c.id and p.status in ('active', 'ending'))
                  and not exists (select 1 from timesheets t where t.consultant_id = c.id and t.week_start = :w
                                   and t.status in ('submitted', 'approved'))""", {"w": last_week})
        if missing:
            names = ", ".join(r["full_name"] for r in missing[:4]) + (" …" if len(missing) > 4 else "")
            out.append(_s(85, "Timesheets", f"{len(missing)} consultant(s) haven't submitted last week",
                          f"{names}. Invoices for these hours can't go out until they do.", "Send reminder",
                          f"/timesheets?week={last_week}&filter=missing"))

    if ctx.allows("finance"):
        overdue = await db.all(
            """select i.id, i.number, co.name, i.balance, i.days_late from invoice_balances i join companies co on co.id = i.company_id
                where i.direction = 'ar' and i.live_status in ('overdue', 'overdue_part_paid') order by i.balance * i.days_late desc limit 5""")
        for inv in overdue:
            out.append(_s(min(99, 70 + inv["days_late"]), "Collections", f"{inv['name']} is {inv['days_late']} days late on {inv['number']}",
                          "Largest balance × days late first. Day 15 copies the account manager; day 30 escalates.",
                          "Log follow-up", f"/invoices/{inv['id']}", inv["balance"]))
        releasable = await db.all(
            """select ap.id, ap.number, coalesce(co.name, k.full_name) as payee, ap.balance from invoice_balances ap
                 left join companies co on co.id = ap.company_id left join consultants k on k.id = ap.consultant_id
                where ap.direction = 'ap' and ap.live_status = 'ready_to_pay'""")
        if releasable:
            total = sum(r["balance"] for r in releasable)
            out.append(_s(75, "Payables", f"{len(releasable)} pay-when-paid invoice(s) can be released",
                          "The client paid the matching invoice, so these vendor invoices are no longer on hold.",
                          "Add to payment run", "/invoices?tab=ap", total))
        exceptions = await db.val("select count(*) from invoices where direction = 'ap' and status = 'exception'")
        if exceptions:
            out.append(_s(78, "Payables", f"{exceptions} vendor invoice(s) don't match approved hours",
                          "Three-way match failed (invoice vs. approved timesheet vs. SOW rate).", "Resolve", "/invoices?tab=ap"))
        uninvoiced = await db.val(
            """select count(distinct t.id) from timesheets t join timesheet_entries e on e.timesheet_id = t.id
                where t.status = 'approved' and e.placement_id is not null
                  and not exists (select 1 from invoices i where i.placement_id = e.placement_id and i.direction = 'ar'
                                   and i.status <> 'void' and e.work_date between i.period_start and i.period_end)""")
        if uninvoiced:
            out.append(_s(72, "Invoicing", f"{uninvoiced} approved timesheet(s) not invoiced yet",
                          "Generate client invoices from approved hours.", "Generate invoices", "/invoices?generate=1"))

    if ctx.allows("legal", "account_manager"):
        for sow in await db.all(
                """select s.id, s.code, coalesce(co.name, k.full_name) as party, b.burn_pct, s.end_date - current_date as days_left
                     from sows s left join sow_burn b on b.sow_id = s.id left join companies co on co.id = s.company_id
                     left join consultants k on k.id = s.consultant_id
                    where s.status = 'active' and (b.burn_pct >= 80 or s.end_date <= current_date + 45)
                    order by s.end_date limit 6"""):
            why = f"{sow['burn_pct']}% of the value is used" if sow["burn_pct"] and sow["burn_pct"] >= 80 else f"ends in {sow['days_left']} days"
            out.append(_s(65 if sow["days_left"] > 14 else 88, "Contracts", f"{sow['code']} ({sow['party']}) {why}",
                          "Start an amendment now so billing doesn't stop.", "Draft amendment", f"/contracts/sows/{sow['id']}"))
        stuck = await db.all(
            """select e.id, e.number, e.title, now()::date - e.sent_at::date as days from envelopes e
                where e.status = 'sent' and e.sent_at < now() - interval '5 days' order by e.sent_at limit 5""")
        for env in stuck:
            out.append(_s(60, "E-signatures", f"{env['number']} unsigned for {env['days']} days", env["title"], "Send reminder",
                          f"/esign/{env['id']}"))

    if ctx.allows("hr", "legal"):
        for doc in await db.all(
                """select d.id, d.label, coalesce(k.full_name, co.name) as owner, d.expires_on - current_date as days, d.status, d.blocks
                     from tracked_documents d left join consultants k on k.id = d.consultant_id left join companies co on co.id = d.company_id
                    where d.active and (d.status = 'missing' or d.expires_on <= current_date + 30) order by d.expires_on nulls first limit 8"""):
            when = "missing" if doc["status"] == "missing" else ("expired" if doc["days"] < 0 else f"expires in {doc['days']} days")
            out.append(_s(95 if doc["status"] == "missing" or doc["days"] <= 7 else 82, "Compliance",
                          f"{doc['owner']}: {doc['label']} {when}",
                          f"Blocks {doc['blocks']} until renewed." if doc["blocks"] else "Collect the renewed document and record the new date.",
                          "Record renewal", f"/compliance?doc={doc['id']}"))
        pending = await db.val("select count(*) from registrations where status = 'pending'")
        if pending:
            out.append(_s(70, "Onboarding", f"{pending} registration(s) waiting for approval",
                          "Check documents, EIN and duplicates, then approve.", "Review", "/compliance?tab=registrations"))

    if ctx.allows("account_manager", "hr"):
        ending = await db.all(
            """select p.id, c.id as consultant_id, c.full_name, pr.name as project, p.end_date - current_date as days from placements p
                 join consultants c on c.id = p.consultant_id join projects pr on pr.id = p.project_id
                where p.status in ('active', 'ending') and p.end_date between current_date and current_date + 30 order by p.end_date""")
        for p in ending:
            out.append(_s(68, "Bench", f"{p['full_name']} rolls off {p['project']} in {p['days']} days",
                          "Extend the assignment or start matching them to open requirements.", "Plan next step", f"/consultants/{p['consultant_id']}"))

    if not ctx.allows("finance"):
        for item in out:
            item["amount"] = None
    out.sort(key=lambda s: s["priority"], reverse=True)
    return out


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@router.post("/ask")
async def ask(body: AskIn, db: TenantDb = Depends(tenant_db)):
    """Plain-English answer grounded only in the caller's own suggestions list."""
    settings = get_settings()
    provider = settings.ai_provider
    if provider == "deepseek" and not settings.deepseek_api_key:
        raise ApiError(501, "ai_disabled", "AI answers are not enabled for this company (DEEPSEEK_API_KEY is not set).")
    if provider == "anthropic" and not settings.anthropic_api_key:
        raise ApiError(501, "ai_disabled", "AI answers are not enabled for this company (ANTHROPIC_API_KEY is not set).")
    items = await suggestions(db)
    context = orjson.dumps([{k: v for k, v in s.items() if k != "link"} for s in items[:40]], default=str).decode()
    system = ("You help staff at a US staffing company decide what to do next in myTrakIn. Answer only from "
              "the JSON list of open items you are given. Be brief and concrete; name the item and the next "
              "step. If the list doesn't answer the question, say so.")
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            if provider == "deepseek":
                response = await client.post(
                    f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                    json={"model": settings.deepseek_model, "temperature": 0.3, "max_tokens": 600,
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": f"Open items:\n{context}\n\nQuestion: {body.question}"}]})
                response.raise_for_status()
                text = (response.json()["choices"][0]["message"].get("content") or "").strip()
            else:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01"},
                    json={"model": settings.ai_model, "max_tokens": 600,
                          "system": system,
                          "messages": [{"role": "user", "content": f"Open items:\n{context}\n\nQuestion: {body.question}"}]})
                response.raise_for_status()
                text = "".join(part.get("text", "") for part in response.json().get("content", []))
    except httpx.HTTPError as exc:
        log.warning("AI request failed: %s", exc)
        raise ApiError(502, "ai_unavailable", "The AI service didn't answer. Try again in a moment.") from exc
    return {"answer": text, "based_on": len(items)}
