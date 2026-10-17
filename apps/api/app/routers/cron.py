"""Daily automatic e-mails, run by Vercel Cron (see vercel.json).

    - document expiry: I-9 reverification, passport, EAD, I-94, COI ... (120/90/60/30/14/7/0 days)
    - timesheets not submitted (Friday, Monday, escalation Tuesday)
    - client invoices: courtesy notice and overdue reminders
    - MSA / SOW expiry alerts
    - e-signature reminders and link expiry
    - new policy versions not yet accepted

Each tenant runs in its own transaction, so one tenant's problem can't stop the others.
A dedupe key per message means running the job twice in a day never sends twice.
"""

from __future__ import annotations

import hmac
import logging
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Request
from sqlalchemy import text

from ..config import get_settings
from ..db import get_engine
from ..deps import TenantDb, open_system
from ..errors import ApiError
from ..services.email import render, send_email
from ..services.esign import send_to_signer
from ..utils import week_start

log = logging.getLogger("mytrakin.cron")
router = APIRouter(prefix="/cron", tags=["scheduled jobs"])

WORK_AUTH_DOCS = {"i9_reverification", "ead", "i94", "visa_notice"}


def _authorize(request: Request) -> None:
    secret = get_settings().cron_secret
    header = request.headers.get("authorization", "")
    if not secret or not hmac.compare_digest(header, f"Bearer {secret}"):
        raise ApiError(401, "unauthorized", "Invalid cron secret")


@router.get("/daily")
async def daily(request: Request):
    _authorize(request)
    async with get_engine().begin() as conn:
        # company drafts nobody finished within 7 days (the wizard was abandoned before a profile existed)
        purged = (await conn.execute(text("select mytrakin.purge_abandoned_accounts()"))).scalar()
        # MSAs past their end date move to expired (they stop counting for billing and project gates).
        expired = (await conn.execute(text("select mytrakin.expire_master_agreements()"))).scalar()
    async with get_engine().connect() as conn:
        tenant_ids = [row[0] for row in (await conn.execute(text("select * from mytrakin.active_tenant_ids()"))).all()]
    summary = {}
    for tenant_id in tenant_ids:
        try:
            async for db in open_system(tenant_id):
                summary[str(tenant_id)] = await run_for_tenant(db, date.today())
        except Exception:   # noqa: BLE001 — log and continue with the next tenant
            log.exception("daily job failed for tenant %s", tenant_id)
            summary[str(tenant_id)] = {"error": True}
    return {"ran_at": datetime.now(UTC), "tenants": len(tenant_ids), "purged_drafts": purged,
            "expired_msas": expired, "summary": summary}


async def run_for_tenant(db: TenantDb, today: date) -> dict:
    # Vercel may deliver the same cron run twice; only one may work on a tenant at a time.
    if not await db.val("select pg_try_advisory_xact_lock(hashtext(:k))", {"k": f"mytrakin-daily:{db.ctx.tenant_id}"}):
        return {"skipped": "already running"}
    rules = {r["key"]: r for r in await db.all("select key, offsets, enabled from reminder_rules")}
    tenant = await db.val("select name from tenants where id = :t", {"t": db.ctx.tenant_id})

    def offsets(key: str) -> set[int]:
        rule = rules.get(key)
        return set(rule["offsets"]) if rule and rule["enabled"] else set()

    staff = {role: [r["email"] for r in await db.all(
        """select p.email from memberships m join profiles p on p.id = m.user_id
            where m.status = 'active' and m.role = any (:roles)""", {"roles": [role, "tenant_admin"]})]
        for role in ("hr", "finance", "legal")}

    sent = {"documents": 0, "timesheets": 0, "invoices": 0, "contracts": 0, "esign": 0, "policies": 0}

    # ---------------------------------------------------------------- expiring documents
    await db.run("update tracked_documents set status = 'expired' where active and status = 'valid' and expires_on < :d", {"d": today})
    docs = await db.all(
        """select d.*, k.full_name as person, k.email as person_email, co.name as company, co.contact_email
             from tracked_documents d left join consultants k on k.id = d.consultant_id left join companies co on co.id = d.company_id
            where d.active and d.expires_on is not null and (k.id is null or k.status <> 'former')""")
    for d in docs:
        days = (d["expires_on"] - today).days
        rule = "work_auth_expiry" if d["doc_type"] in WORK_AUTH_DOCS else "document_expiry"
        if days not in offsets(rule) and not (days < 0 and days % 7 == 0):   # weekly after expiry until renewed
            continue
        who = d["person"] or d["company"]
        to = list({*d["recipients"], *staff["hr"], *([d["person_email"]] if d["person_email"] else []),
                   *([d["contact_email"]] if d["company"] and d["contact_email"] else [])})
        when = f"expired {-days} days ago" if days < 0 else ("expires today" if days == 0 else f"expires in {days} days")
        lines = [f"{who}: {d['label']} {when} ({d['expires_on']:%b %d, %Y})."]
        if d["doc_type"] == "i9_reverification":
            lines.append("Complete Form I-9 Supplement B (reverification) before the expiry date. Work can't continue after it "
                         "without a valid document.")
        if d["blocks"]:
            lines.append(f"Until it's renewed, {d['blocks']} are on hold.")
        lines.append("Upload the renewed document or reply to HR.")
        if await send_email(db, to=to, subject=f"{'Action needed: ' if days <= 7 else ''}{d['label']} — {who} {when}",
                            kind="document_expiry", tenant_id=db.ctx.tenant_id, ref_type="tracked_document", ref_id=d["id"],
                            dedupe_key=f"doc:{d['id']}:{d['expires_on']}:{days}",
                            html_body=render(f"{d['label']} {when}", lines)):
            sent["documents"] += 1
            await db.run("update tracked_documents set last_notified_on = :d where id = :id", {"d": today, "id": d["id"]})

    # ---------------------------------------------------------------- timesheets
    # Weeks run Sunday–Saturday. Friday (0) = this week is due; Monday (3) / Tuesday (4) = last week is late.
    weekday_offset = {4: 0, 0: 3, 1: 4}.get(today.weekday())
    if weekday_offset is not None and weekday_offset in offsets("timesheet_due"):
        week = week_start(today) if weekday_offset == 0 else week_start(today) - timedelta(days=7)
        missing = await db.all(
            """select c.id, c.full_name, c.email from consultants c
                where c.status = 'active' and c.email is not null
                  and exists (select 1 from placements p where p.consultant_id = c.id and p.status in ('active', 'ending')
                               and p.start_date <= cast(:w as date) + 6)
                  and not exists (select 1 from timesheets t where t.consultant_id = c.id and t.week_start = :w
                                   and t.status in ('submitted', 'approved'))""", {"w": week})
        for c in missing:
            escalate = weekday_offset == 4
            if await send_email(db, to=[c["email"], *(staff["hr"] if escalate else [])],
                                subject=f"{'Overdue' if weekday_offset else 'Reminder'}: timesheet for the week of {week:%b %d}",
                                kind="timesheet_reminder", tenant_id=db.ctx.tenant_id, ref_type="consultant", ref_id=c["id"],
                                dedupe_key=f"ts:{c['id']}:{week}:{weekday_offset}",
                                html_body=render(f"Hi {c['full_name'].split()[0]}, please submit your timesheet",
                                                 [f"Your timesheet for the week of {week:%B %d} hasn't been submitted.",
                                                  "Approved hours are what we invoice and pay from, so late timesheets delay payments."],
                                                 button=("Open my timesheet", f"{get_settings().web_origin}/my/timesheet"))):
                sent["timesheets"] += 1

    # ---------------------------------------------------------------- client invoices (AR)
    courtesy, overdue = offsets("ar_courtesy"), offsets("ar_overdue")
    invoices = await db.all(
        """select i.id, i.number, i.balance, i.due_on, i.days_late, i.live_status, co.name, co.contact_email, co.contact_name
             from invoice_balances i join companies co on co.id = i.company_id
            where i.direction = 'ar' and i.status <> 'draft'          -- never remind a customer about an unsent invoice
              and i.live_status not in ('paid', 'void') and i.due_on is not null and co.contact_email is not null""")
    for inv in invoices:
        days = (inv["due_on"] - today).days
        if -days in courtesy or (days < 0 and -days in overdue):
            late = days < 0
            to = [inv["contact_email"], *(staff["finance"] if late and -days >= 30 else [])]
            if await send_email(db, to=to,
                                subject=f"{tenant} invoice {inv['number']} {'is ' + str(-days) + ' days past due' if late else 'is due ' + format(inv['due_on'], '%b %d')}",
                                kind="ar_reminder", tenant_id=db.ctx.tenant_id, ref_type="invoice", ref_id=inv["id"],
                                dedupe_key=f"ar:{inv['id']}:{days}",
                                html_body=render(f"Invoice {inv['number']}",
                                                 [f"Hello {inv['contact_name'] or inv['name']},",
                                                  f"Balance due: ${inv['balance']:,.2f}, due {inv['due_on']:%B %d, %Y}.",
                                                  "If it's already on its way, thank you — please ignore this note or reply with "
                                                  "the payment reference." if late else "This is a courtesy reminder ahead of the due date."])):
                sent["invoices"] += 1

    # ---------------------------------------------------------------- contract expiry
    for row in await db.all(
            """select 'agreement' as kind, a.id, a.code, a.expires_on as ends, coalesce(co.name, k.full_name) as party
                 from agreements a left join companies co on co.id = a.company_id left join consultants k on k.id = a.consultant_id
                where a.status = 'active' and a.expires_on is not null
               union all
               select 'sow', s.id, s.code, s.end_date, coalesce(co.name, k.full_name)
                 from sows s left join companies co on co.id = s.company_id left join consultants k on k.id = s.consultant_id
                where s.status = 'active'"""):
        days_left = (row["ends"] - today).days
        if -days_left not in offsets("contract_expiry"):     # offsets are negative: days before the end
            continue
        sent_ok = await send_email(
            db, to=staff["legal"], subject=f"{row['code']} ({row['party']}) ends in {days_left} days",
            kind="contract_expiry", tenant_id=db.ctx.tenant_id, ref_type=row["kind"], ref_id=row["id"],
            dedupe_key=f"contract:{row['id']}:{row['ends']}:{days_left}",
            html_body=render(f"{row['code']} ends {row['ends']:%B %d, %Y}",
                             [f"{row['party']}: renew, amend or plan the wind-down.",
                              "Placements under it can't be invoiced after the end date."]))
        sent["contracts"] += int(sent_ok)

    # ---------------------------------------------------------------- e-signatures
    await db.run("update envelopes set status = 'expired' where status = 'sent' and expires_at < now()")
    for env in await db.all("select * from envelopes where status = 'sent'"):
        for signer in await db.all(
                """select * from envelope_signers where envelope_id = :id and status in ('sent', 'viewed')
                      and coalesce(last_reminded_at, :sent) < now() - make_interval(days => :every)""",
                {"id": env["id"], "sent": env["sent_at"], "every": env["remind_every_days"]}):
            await send_to_signer(db, envelope=env, signer=signer, sender_name=env["sent_by_name"] or tenant, is_reminder=True)
            sent["esign"] += 1

    # ---------------------------------------------------------------- policies
    for row in await db.all(
            """select po.id as policy_id, po.name, po.version, po.effective_on, c.id as consultant_id, c.full_name, c.email
                 from policies po join consultants c on c.status = 'active' and c.engagement = any (po.applies_to) and c.email is not null
                where po.active and not exists (select 1 from policy_acceptances pa where pa.policy_id = po.id and pa.consultant_id = c.id)"""):
        days_since = (today - row["effective_on"]).days
        if days_since not in offsets("policy_acceptance"):
            continue
        sent_ok = await send_email(
            db, to=row["email"], subject=f"Please review and accept: {row['name']} {row['version']}",
            kind="policy", tenant_id=db.ctx.tenant_id, ref_type="policy", ref_id=row["policy_id"],
            dedupe_key=f"policy:{row['policy_id']}:{row['consultant_id']}:{days_since}",
            html_body=render(f"{row['name']} {row['version']}",
                             [f"Hi {row['full_name'].split()[0]}, {tenant} published an updated policy.",
                              "Please read it and confirm in myTrakIn. It takes about a minute."],
                             button=("Review policy", f"{get_settings().web_origin}/my/policies")))
        sent["policies"] += int(sent_ok)

    return sent
