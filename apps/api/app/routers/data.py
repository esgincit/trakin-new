"""Import and export.

    GET  /data/templates                 what can be imported, with column help
    GET  /data/templates/{key}.csv       blank template with sample rows
    POST /data/import/{key}?dry_run=1    check a file without saving anything
    POST /data/import/{key}              import (row by row; a bad row never blocks the good ones)
    GET  /data/export/{key}.csv          export (same columns as the template, so files round-trip)
"""

from __future__ import annotations

from datetime import date

import orjson
from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.exc import DBAPIError

from ..deps import TenantDb, tenant_db
from ..errors import ApiError, bad_request, forbidden, not_found
from ..services.csv_io import TEMPLATES, parse, to_csv, validate

router = APIRouter(prefix="/data", tags=["import & export"])

MAX_IMPORT_BYTES = 4 * 1024 * 1024     # Vercel request bodies are limited to 4.5 MB
MAX_IMPORT_ROWS = 5000


def _csv_response(text: str, filename: str) -> Response:
    # The BOM makes Excel open UTF-8 correctly.
    return Response("﻿" + text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@router.get("/templates")
async def templates(db: TenantDb = Depends(tenant_db)):
    return [
        {"key": t.key, "label": t.label, "can_import": db.ctx.allows(*t.roles),
         "columns": [{"name": c.name, "required": c.required, "kind": c.kind, "choices": list(c.choices)} for c in t.columns]}
        for t in TEMPLATES.values()
    ]


@router.get("/templates/{key}.csv")
async def template_csv(key: str):
    template = TEMPLATES.get(key)
    if template is None:
        raise not_found("Template")
    return _csv_response(to_csv([template.header, *template.sample]), f"mytrakin-{key}-template.csv")


@router.post("/import/{key}")
async def import_csv(key: str, file: UploadFile = File(), dry_run: bool = Query(False), db: TenantDb = Depends(tenant_db)):
    template = TEMPLATES.get(key)
    if template is None or template.importer is None:
        raise not_found("Template")
    if not db.ctx.allows(*template.roles):
        raise forbidden("Your role can't import this data")

    raw = await file.read()
    if len(raw) > MAX_IMPORT_BYTES:
        raise bad_request("The file is larger than 4 MB — split it into smaller files")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")   # files saved from older Excel versions
    header, rows = parse(text)
    if not rows:
        raise bad_request("The file has no data rows")
    if len(rows) > MAX_IMPORT_ROWS:
        raise bad_request(f"At most {MAX_IMPORT_ROWS} rows per file")

    missing, results = validate(template, header, rows)
    if missing:
        raise bad_request(f"Missing columns: {', '.join(missing)}. Download the template to see the expected header.")
    unknown = [h for h in header if h not in template.header]

    errors = [{"line": r.line, "errors": r.errors} for r in results if r.errors]
    if dry_run:
        return {"dry_run": True, "rows": len(results), "valid": len(results) - len(errors), "errors": errors,
                "ignored_columns": unknown}

    created = updated = 0
    for result in results:
        if result.errors:
            continue
        try:
            async with db.conn.begin_nested():          # savepoint: one failing row rolls back alone
                outcome = await template.importer(db, db.ctx.tenant_id, result.values)
        except ApiError as exc:
            errors.append({"line": result.line, "errors": [exc.message]})
            continue
        except (DBAPIError, ValueError, LookupError) as exc:
            errors.append({"line": result.line, "errors": [_explain(exc)]})
            continue
        if outcome == "updated":
            updated += 1
        else:
            created += 1

    errors.sort(key=lambda e: e["line"])
    job = await db.one(
        """insert into import_jobs (tenant_id, entity, filename, total_rows, imported_rows, updated_rows, errors, created_by)
           values (:t, :e, :f, :total, :c, :u, cast(:err as jsonb), :by) returning id, created_at""",
        {"t": db.ctx.tenant_id, "e": key, "f": file.filename, "total": len(results), "c": created, "u": updated,
         "err": orjson.dumps(errors).decode(), "by": db.ctx.user_id})
    return {"job_id": job["id"], "rows": len(results), "created": created, "updated": updated, "errors": errors,
            "ignored_columns": unknown}


def _explain(exc: Exception) -> str:
    if isinstance(exc, DBAPIError):
        message = str(exc.orig).splitlines()[0] if exc.orig else "database error"
        if "violates row-level security" in message or "permission denied" in message:
            return "Your role can't create this record"
        if "duplicate key" in message:
            return "A record with the same key already exists"
        if "foreign key" in message:
            return "Refers to a record that doesn't exist"
        return message[:200]
    return str(exc)[:200]


@router.get("/import-jobs")
async def import_jobs(db: TenantDb = Depends(tenant_db)):
    return await db.all(
        """select j.id, j.entity, j.filename, j.total_rows, j.imported_rows, j.updated_rows,
                  jsonb_array_length(j.errors) as error_count, j.created_at, p.full_name as by
             from import_jobs j left join profiles p on p.id = j.created_by order by j.created_at desc limit 100""")


# ============================================================================ export
_KIND_LABEL = "case c.kind when 'client' then 'Client' when 'prime_vendor' then 'Prime vendor' when 'vendor' then 'Vendor' else 'End client' end"
_ENG_LABEL = ("case c.engagement when 'w2_fulltime' then 'W-2 full-time' when 'w2_contract' then 'W-2 contract' "
              "when 'c2c' then 'C2C' else '1099' end")

EXPORTS: dict[str, tuple[tuple[str, ...], str]] = {
    "companies": (("tenant_admin", "finance", "account_manager", "legal", "hr", "viewer"), f"""
        select c.name as "Legal name", {_KIND_LABEL} as "Type", c.ein as "EIN", c.state as "State",
               c.contact_name as "Contact name", c.contact_email as "Contact email", c.default_terms as "Default payment terms",
               a.code as "Existing MSA ID", a.effective_on as "MSA effective date", a.expires_on as "MSA expiry date",
               initcap(c.status) as "Status", c.inactive_since as "Inactive since", c.inactive_reason as "Inactive reason"
          from companies c
          left join lateral (select code, effective_on, expires_on from agreements
                              where company_id = c.id and kind in ('msa', 'subcontract') order by effective_on desc limit 1) a on true
         order by c.status, c.name"""),
    "consultants": (("tenant_admin", "hr", "account_manager", "legal", "viewer"), f"""
        select c.full_name as "Full name", c.email as "Email", c.phone as "Mobile", {_ENG_LABEL} as "Engagement type",
               e.name as "Employer (C2C only)", c.title as "Job title", c.start_date as "Start date", c.location as "Work location",
               initcap(c.status) as "Status", c.end_date as "End date (former only)", c.leave_reason as "Reason for leaving",
               case c.rehire_eligible when true then 'Y' when false then 'N' end as "Eligible for rehire (Y/N)"
          from consultants c left join companies e on e.id = c.employer_company_id order by c.status, c.full_name"""),
    "projects": (("tenant_admin", "account_manager", "finance", "viewer"), """
        select p.code as "Project code", p.name as "Project name", cl.name as "Client", pm.name as "Prime vendor (if any)",
               p.start_date as "Start date", p.end_date as "End date", p.client_approver as "Client timesheet approver",
               p.description as "Description"
          from projects p left join companies cl on cl.id = p.client_company_id left join companies pm on pm.id = p.prime_company_id
         order by p.code"""),
    "agreements": (("tenant_admin", "legal", "account_manager", "finance"), """
        select a.code as "Agreement ID",
               case a.kind when 'msa' then 'MSA' when 'subcontract' then 'Subcontractor agreement'
                    when 'ica' then 'Independent contractor agreement (1099)' when 'nda' then 'NDA' else 'Offer letter' end as "Type",
               coalesce(co.name, k.full_name) as "Counterparty", initcap(a.tenant_side) as "Tenant is (Supplier / Buyer)",
               a.effective_on as "Effective date", a.expires_on as "Expiry date", a.payment_terms as "Payment terms",
               a.renewal as "Renewal", a.notice_period as "Notice period", a.insurance_required as "Insurance required",
               a.status as "Status", a.source as "Source"
          from agreements a left join companies co on co.id = a.company_id left join consultants k on k.id = a.consultant_id
         order by a.code"""),
    "sows": (("tenant_admin", "legal", "account_manager", "finance"), """
        select s.code as "SOW ID", a.code as "Agreement ID", case s.side when 'we_bill' then 'We bill' else 'We pay' end as "Side (We bill / We pay)",
               s.title as "Title", s.start_date as "Start date", s.end_date as "End date", s.value_cap as "Value (ceiling)",
               b.invoiced as "Invoiced to date", b.collected_or_paid as "Collected or paid to date", s.status as "Status"
          from sows s join agreements a on a.id = s.agreement_id left join sow_burn b on b.sow_id = s.id order by s.code"""),
    "placements": (("tenant_admin", "account_manager", "finance"), """
        select c.email as "Consultant (email or name)", pr.code as "Project code", p.role_title as "Role", p.start_date as "Start date",
               p.end_date as "End date", p.hours_per_week as "Hours per week", ar.name as "AR customer (who we bill)",
               ars.code as "AR SOW ID", p.bill_rate as "AR bill rate", p.ar_terms as "AR terms",
               coalesce(ap.name, apc.full_name) as "AP payee (vendor or 1099 name)", aps.code as "AP SOW ID",
               p.pay_rate as "AP pay rate", p.ap_terms as "AP terms", case when p.pay_when_paid then 'Y' else 'N' end as "Pay when paid (Y/N)",
               p.status as "Status"
          from placements p join consultants c on c.id = p.consultant_id join projects pr on pr.id = p.project_id
          left join companies ar on ar.id = p.ar_company_id left join companies ap on ap.id = p.ap_company_id
          left join consultants apc on apc.id = p.ap_consultant_id
          left join sows ars on ars.id = p.ar_sow_id left join sows aps on aps.id = p.ap_sow_id
         order by c.full_name, p.start_date"""),
    "ar_invoices": (("tenant_admin", "finance"), """
        select i.number as "Invoice number", co.name as "Customer", s.code as "SOW ID", i.period_start as "Period start",
               i.period_end as "Period end", i.hours as "Hours", i.rate as "Rate", i.amount as "Amount", i.issued_on as "Issued",
               i.due_on as "Due date", i.terms as "Terms", i.paid as "Already paid", i.balance as "Balance", i.live_status as "Status"
          from invoice_balances i left join companies co on co.id = i.company_id left join sows s on s.id = i.sow_id
         where i.direction = 'ar' order by i.issued_on desc nulls last"""),
    "ap_invoices": (("tenant_admin", "finance"), """
        select i.number as "Invoice number", coalesce(co.name, k.full_name) as "Payee", s.code as "SOW ID",
               i.period_start as "Period start", i.period_end as "Period end", i.hours as "Hours", i.rate as "Rate",
               i.amount as "Amount", i.issued_on as "Issued", i.due_on as "Due date", i.terms as "Terms",
               i.paid as "Already paid", i.balance as "Balance", i.live_status as "Status"
          from invoice_balances i left join companies co on co.id = i.company_id left join consultants k on k.id = i.consultant_id
          left join sows s on s.id = i.sow_id
         where i.direction = 'ap' order by i.issued_on desc nulls last"""),
    "timesheets": (("tenant_admin", "finance", "account_manager", "hr", "approver", "viewer"), """
        select c.full_name as "Consultant", coalesce(pr.code, 'Internal') as "Project code", t.week_start as "Week starting",
               sum(e.hours) as "Hours", t.status as "Status", t.submitted_at as "Submitted",
               t.decided_at as "Approved / rejected", t.reject_reason as "Reason"
          from timesheets t join consultants c on c.id = t.consultant_id
          join timesheet_entries e on e.timesheet_id = t.id
          left join placements p on p.id = e.placement_id left join projects pr on pr.id = p.project_id
         group by t.id, c.full_name, pr.code
         order by t.week_start desc, c.full_name"""),
    "tracked_documents": (("tenant_admin", "hr", "legal"), """
        select coalesce(k.full_name, co.name) as "Person or company", d.doc_type as "Document type", d.label as "Label",
               d.expires_on as "Expires on", array_to_string(d.recipients, ';') as "Email recipients (; separated)", d.status as "Status"
          from tracked_documents d left join consultants k on k.id = d.consultant_id left join companies co on co.id = d.company_id
         where d.active order by d.expires_on nulls last"""),
    "payments": (("tenant_admin", "finance"), """
        select pm.paid_on as "Date", i.number as "Invoice", i.direction as "Direction", pm.amount as "Amount",
               pm.method as "Method", pm.reference as "Reference"
          from payments pm join invoices i on i.id = pm.invoice_id order by pm.paid_on desc"""),
    "payroll": (("tenant_admin", "finance"), """
        select c.email as "Employee (email or name)", pl.period_start as "Period start", pl.period_end as "Period end",
               pl.pay_date as "Pay date", pl.hours as "Hours", pl.gross as "Gross pay", pl.employer_taxes as "Employer taxes",
               pl.benefits as "Benefits", pl.net as "Net pay"
          from payroll_lines pl join consultants c on c.id = pl.consultant_id order by pl.pay_date desc"""),
    "audit": (("tenant_admin", "legal", "finance"), """
        select a.at as "When", coalesce(p.full_name, a.actor_role) as "Who", a.actor_role as "Role", a.action as "Action",
               a.entity as "Record type", a.entity_id as "Record id", a.ip as "IP address", a.changes::text as "Changes"
          from audit_log a left join profiles p on p.id = a.actor_id order by a.at desc limit 10000"""),
}


@router.get("/export/{key}.csv")
async def export_csv(key: str, db: TenantDb = Depends(tenant_db)):
    if key not in EXPORTS:
        raise not_found("Export")
    roles, sql = EXPORTS[key]
    if not db.ctx.allows(*roles):
        raise forbidden("Your role can't export this data")
    rows = await db.all(sql)
    header = list(rows[0].keys()) if rows else _header_for(key)
    return _csv_response(to_csv([header, *[list(r.values()) for r in rows]]), f"mytrakin-{key}-{date.today():%Y-%m-%d}.csv")


def _header_for(key: str) -> list[str]:
    template = TEMPLATES.get(key)
    return template.header if template else []
