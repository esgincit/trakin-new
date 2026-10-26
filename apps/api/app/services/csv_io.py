"""CSV templates, validation and imports for bringing existing data into myTrakIn.

Every entity has: the column list (required ones marked), sample rows that also act
as documentation, a row validator and an importer. Imports run in the caller's
transaction and RLS, so a user can only import what they could create by hand.
Rows are matched on a natural key (company name, e-mail, code ...) so re-importing
the same file updates instead of duplicating.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from ..db import Db

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Sensitive rows are tagged by stable IDs, not names, so imports never mis-match:
# companies carry Business IDs (C-0006, assigned by the onboarding trigger) and
# people carry system user codes (U000123). Both are accepted anywhere a company
# or consultant is referenced.
ID_COMPANY_RE = re.compile(r"^C-\d{3,6}$", re.I)
ID_USER_RE = re.compile(r"^U\d{6}$", re.I)


@dataclass
class Column:
    name: str
    required: bool = False
    kind: str = "text"            # text | date | number | email | choice | bool
    choices: tuple[str, ...] = ()


@dataclass
class Template:
    key: str
    label: str
    columns: list[Column]
    sample: list[list[str]]
    importer: Callable[[Db, Any, dict[str, str]], Awaitable[str]] | None = None   # returns "created" | "updated"
    roles: tuple[str, ...] = ("tenant_admin",)

    @property
    def header(self) -> list[str]:
        return [c.name for c in self.columns]


@dataclass
class RowResult:
    line: int
    values: dict[str, str]
    errors: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------- parsing
def _cell(value: Any) -> Any:
    """Neutralise spreadsheet formulas (CSV injection): text starting with = + - @ is prefixed with '."""
    if value is None:
        return ""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def to_csv(rows: list[list[Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for row in rows:
        writer.writerow([_cell(v) for v in row])
    return buffer.getvalue()


def parse(text: str) -> tuple[list[str], list[dict[str, str]]]:
    text = text.lstrip("﻿")   # Excel's UTF-8 byte-order mark
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        return [], []
    header = [h.strip() for h in rows[0]]
    return header, [{h: _uncell(r[i]) if i < len(r) else "" for i, h in enumerate(header)} for r in rows[1:]]


def _uncell(value: str) -> str:
    """Undo the formula guard added by our own exports ('+1 555 … → +1 555 …)."""
    value = value.strip()
    if value[:1] == "'" and value[1:2] in ("=", "+", "-", "@"):
        return value[1:]
    return value


def validate(template: Template, header: list[str], rows: list[dict[str, str]]) -> tuple[list[str], list[RowResult]]:
    missing = [c.name for c in template.columns if c.required and c.name not in header]
    results: list[RowResult] = []
    for i, row in enumerate(rows, start=2):
        result = RowResult(line=i, values=row)
        for col in template.columns:
            value = row.get(col.name, "")
            if col.required and not value:
                result.errors.append(f"{col.name} is empty")
                continue
            if not value:
                continue
            if col.kind == "date" and not DATE_RE.match(value):
                result.errors.append(f"{col.name} must be YYYY-MM-DD")
            elif col.kind == "number":
                try:
                    Decimal(value.replace(",", "").replace("$", ""))
                except InvalidOperation:
                    result.errors.append(f"{col.name} must be a number")
            elif col.kind == "email" and not EMAIL_RE.match(value):
                result.errors.append(f"{col.name} is not a valid e-mail")
            elif col.kind == "choice" and value.lower() not in {c.lower() for c in col.choices}:
                result.errors.append(f"{col.name} must be one of: {', '.join(col.choices)}")
            elif col.kind == "bool" and value.lower() not in {"y", "n", "yes", "no", "true", "false"}:
                result.errors.append(f"{col.name} must be Y or N")
        results.append(result)
    return missing, results


def _num(value: str | None) -> Decimal | None:
    if not value:
        return None
    return Decimal(value.replace(",", "").replace("$", ""))


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _bool(value: str | None) -> bool | None:
    if not value:
        return None
    return value.lower() in {"y", "yes", "true"}


async def _company_id(db: Db, name_or_id: str | None) -> Any:
    """Match a company by Business ID first (C-0006), then by exact legal name."""
    if not name_or_id:
        return None
    key = name_or_id.strip()
    if ID_COMPANY_RE.match(key):
        return await db.val("select id from companies where upper(business_code) = upper(:k)", {"k": key})
    return await db.val("select id from companies where lower(name) = lower(:n)", {"n": key})


async def _consultant_id(db: Db, key: str | None) -> Any:
    """Match a consultant by system user code (U000123) first, then e-mail, then name.
    The U-code lookup goes through the SECURITY DEFINER helper (RLS hides user_codes)."""
    if not key:
        return None
    k = key.strip()
    if ID_USER_RE.match(k):
        return await db.val("select mytrakin.consultant_by_code(:k)", {"k": k})
    return await db.val("select id from consultants where lower(email::text) = lower(:k) or lower(full_name) = lower(:k) "
                        "order by status = 'active' desc limit 1", {"k": k})


ENGAGEMENTS = {"w-2 full-time": "w2_fulltime", "w2_fulltime": "w2_fulltime", "w-2 contract": "w2_contract",
               "w2_contract": "w2_contract", "c2c": "c2c", "e2e": "e2e", "1099": "1099"}
VENDOR_EMPLOYED = {"c2c", "e2e"}
COMPANY_KINDS = {"client": "client", "prime vendor": "prime_vendor", "prime_vendor": "prime_vendor",
                 "vendor": "vendor", "c2c vendor": "vendor", "end client": "end_client", "end_client": "end_client"}


# ----------------------------------------------------------------------------- importers
async def import_company(db: Db, tenant: Any, r: dict[str, str]) -> str:
    kind = COMPANY_KINDS[r["Type"].lower()]
    inactive = (r.get("Status") or "").lower() == "inactive"
    # Sensitive identity: match by Business ID (C-0006) when given, name otherwise.
    existing = await _company_id(db, r.get("Business ID") or r["Legal name"])
    params = {"t": tenant, "name": r["Legal name"], "kind": kind, "ein": r.get("EIN") or None, "state": r.get("State") or None,
              "cn": r.get("Contact name") or None, "ce": r.get("Contact email") or None,
              "terms": r.get("Default payment terms") or "Net 30", "status": "inactive" if inactive else "active",
              "since": _date(r.get("Inactive since")), "why": r.get("Inactive reason") or None, "id": existing}
    if existing:
        await db.run("""update companies set kind=:kind, kinds=cast(array[:kind] as text[]), ein=coalesce(:ein, ein), state=coalesce(:state, state),
                        contact_name=coalesce(:cn, contact_name), contact_email=coalesce(:ce, contact_email),
                        default_terms=:terms, status=:status, inactive_since=:since, inactive_reason=:why where id=:id""", params)
        company_id, result = existing, "updated"
    else:
        company_id = await db.val("""insert into companies (tenant_id, name, kind, kinds, ein, state, contact_name, contact_email,
                                     default_terms, status, onboarding_stage, inactive_since, inactive_reason)
                                     values (:t, :name, :kind, cast(array[:kind] as text[]), :ein, :state, :cn, :ce, :terms, :status, 3, :since, :why)
                                     returning id""", params)
        result = "created"
    if r.get("Existing MSA ID"):
        await db.run(
            """insert into agreements (tenant_id, code, kind, company_id, tenant_side, effective_on, expires_on, payment_terms,
                                       status, source)
               values (:t, :code, :kind, :co, :side, :eff, :exp, :terms, 'active', 'imported')
               on conflict (tenant_id, code) do update set expires_on = excluded.expires_on, effective_on = excluded.effective_on""",
            {"t": tenant, "code": r["Existing MSA ID"], "kind": "subcontract" if kind == "vendor" else "msa", "co": company_id,
             "side": "buyer" if kind == "vendor" else "supplier", "eff": _date(r.get("MSA effective date")),
             "exp": _date(r.get("MSA expiry date")), "terms": params["terms"]},
        )
    return result


async def import_consultant(db: Db, tenant: Any, r: dict[str, str]) -> str:
    engagement = ENGAGEMENTS[r["Engagement type"].lower()]
    status = {"active": "active", "former": "former"}.get((r.get("Status") or "").lower(), "onboarding")
    employer = await _company_id(db, r.get("Employer (C2C only)")) if engagement in VENDOR_EMPLOYED else None
    # Sensitive identity: match by system user code (U000123) when given.
    existing = await _consultant_id(db, r.get("Consultant ID") or r.get("Email") or r["Full name"])
    params = {"t": tenant, "name": r["Full name"], "email": r.get("Email") or None, "phone": r.get("Mobile") or None,
              "eng": engagement, "emp": employer, "title": r.get("Job title") or None, "loc": r.get("Work location") or None,
              "status": status, "start": _date(r.get("Start date")), "end": _date(r.get("End date (former only)")),
              "why": r.get("Reason for leaving") or None, "rehire": _bool(r.get("Eligible for rehire (Y/N)")), "id": existing}
    if engagement in VENDOR_EMPLOYED and employer is None:
        raise ValueError("Employer (C2C only) must match an existing vendor company (C2C and E2E)")
    if existing:
        await db.run("""update consultants set full_name=:name, email=coalesce(:email, email), phone=coalesce(:phone, phone),
                        engagement=:eng, employer_company_id=:emp, title=coalesce(:title, title), location=coalesce(:loc, location),
                        status=:status, start_date=coalesce(:start, start_date), end_date=:end, leave_reason=:why,
                        rehire_eligible=:rehire where id=:id""", params)
        return "updated"
    await db.run("""insert into consultants (tenant_id, full_name, email, phone, engagement, employer_company_id, title, location,
                    status, start_date, end_date, leave_reason, rehire_eligible)
                    values (:t, :name, :email, :phone, :eng, :emp, :title, :loc, :status, :start, :end, :why, :rehire)""", params)
    return "created"


async def import_project(db: Db, tenant: Any, r: dict[str, str]) -> str:
    params = {"t": tenant, "code": r["Project code"], "name": r["Project name"],
              "client": await _company_id(db, r.get("Client")), "prime": await _company_id(db, r.get("Prime vendor (if any)")),
              "start": _date(r.get("Start date")), "end": _date(r.get("End date")), "desc": r.get("Description") or None,
              "approver": r.get("Client timesheet approver") or None}
    updated = await db.run("""update projects set name=:name, client_company_id=:client, prime_company_id=:prime,
                              start_date=coalesce(:start, start_date), end_date=coalesce(:end, end_date),
                              description=coalesce(:desc, description), client_approver=coalesce(:approver, client_approver)
                              where code=:code""", params)
    if updated:
        return "updated"
    await db.run("""insert into projects (tenant_id, code, name, client_company_id, prime_company_id, start_date, end_date,
                    description, client_approver) values (:t, :code, :name, :client, :prime, :start, :end, :desc, :approver)""", params)
    return "created"


async def import_agreement(db: Db, tenant: Any, r: dict[str, str]) -> str:
    kind = {"msa": "msa", "subcontractor agreement": "subcontract", "subcontract": "subcontract",
            "independent contractor agreement (1099)": "ica", "ica": "ica", "nda": "nda", "offer letter": "offer_letter"}[r["Type"].lower()]
    company = await _company_id(db, r["Counterparty"])
    consultant = None if company else await _consultant_id(db, r["Counterparty"])
    if not company and not consultant:
        raise ValueError("Counterparty must match a company or consultant already in myTrakIn")
    result = await db.val(
        """insert into agreements (tenant_id, code, kind, company_id, consultant_id, tenant_side, effective_on, expires_on,
                                   payment_terms, renewal, notice_period, insurance_required, status, source)
           values (:t, :code, :kind, :co, :con, :side, :eff, :exp, :terms, :renew, :notice, :ins, 'active', 'imported')
           on conflict (tenant_id, code) do update set expires_on = excluded.expires_on, payment_terms = excluded.payment_terms,
                 renewal = excluded.renewal, notice_period = excluded.notice_period, insurance_required = excluded.insurance_required
           returning (xmax = 0)""",
        {"t": tenant, "code": r["Agreement ID"], "kind": kind, "co": company, "con": consultant,
         "side": (r.get("Tenant is (Supplier / Buyer)") or "supplier").lower(), "eff": _date(r["Effective date"]),
         "exp": _date(r["Expiry date"]), "terms": r.get("Payment terms") or None, "renew": r.get("Renewal") or None,
         "notice": r.get("Notice period") or None, "ins": r.get("Insurance required") or None},
    )
    return "created" if result else "updated"


async def import_sow(db: Db, tenant: Any, r: dict[str, str]) -> str:
    agreement = await db.one("select id, company_id, consultant_id from agreements where code = :c", {"c": r["Agreement ID"]})
    if agreement is None:
        raise ValueError(f"Agreement {r['Agreement ID']} not found — import agreements first")
    side = "we_pay" if "pay" in (r.get("Side (We bill / We pay)") or "").lower() else "we_bill"
    result = await db.val(
        """insert into sows (tenant_id, code, agreement_id, side, company_id, consultant_id, title, start_date, end_date,
                             value_cap, prior_invoiced, prior_paid)
           values (:t, :code, :ag, :side, :co, :con, :title, :start, :end, :cap, :pi, :pp)
           on conflict (tenant_id, code) do update set end_date = excluded.end_date, value_cap = excluded.value_cap,
                 prior_invoiced = excluded.prior_invoiced, prior_paid = excluded.prior_paid, title = excluded.title
           returning (xmax = 0)""",
        {"t": tenant, "code": r["SOW ID"], "ag": agreement["id"], "side": side, "co": agreement["company_id"],
         "con": agreement["consultant_id"], "title": r.get("Title") or r["SOW ID"], "start": _date(r["Start date"]),
         "end": _date(r["End date"]), "cap": _num(r.get("Value (ceiling)")), "pi": _num(r.get("Invoiced before myTrakIn")) or 0,
         "pp": _num(r.get("Collected or paid before myTrakIn")) or 0},
    )
    return "created" if result else "updated"


async def import_placement(db: Db, tenant: Any, r: dict[str, str]) -> str:
    consultant = await _consultant_id(db, r["Consultant (email or name)"])
    project = await db.val("select id from projects where code = :c", {"c": r["Project code"]})
    if not consultant or not project:
        raise ValueError("Consultant and project must exist before importing placements")
    ap_company = await _company_id(db, r.get("AP payee (vendor or 1099 name)"))
    ap_consultant = None if ap_company else await _consultant_id(db, r.get("AP payee (vendor or 1099 name)"))
    await db.run(
        """insert into placements (tenant_id, consultant_id, project_id, role_title, start_date, end_date, hours_per_week,
                                   ar_company_id, ar_sow_id, bill_rate, ar_terms, ap_company_id, ap_consultant_id, ap_sow_id,
                                   pay_rate, ap_terms, pay_when_paid)
           values (:t, :con, :proj, :role, :start, :end, :hpw, :arco,
                   (select id from sows where code = :arsow), :bill, :arterms, :apco, :apcon,
                   (select id from sows where code = :apsow), :pay, :apterms, :pwp)""",
        {"t": tenant, "con": consultant, "proj": project, "role": r.get("Role") or None, "start": _date(r["Start date"]),
         "end": _date(r.get("End date")), "hpw": _num(r.get("Hours per week")) or 40,
         "arco": await _company_id(db, r["AR customer (who we bill)"]), "arsow": r.get("AR SOW ID") or None,
         "bill": _num(r["AR bill rate"]), "arterms": r.get("AR terms") or None, "apco": ap_company, "apcon": ap_consultant,
         "apsow": r.get("AP SOW ID") or None, "pay": _num(r.get("AP pay rate")), "apterms": r.get("AP terms") or None,
         "pwp": bool(_bool(r.get("Pay when paid (Y/N)")))},
    )
    return "created"


async def import_invoice(db: Db, tenant: Any, r: dict[str, str], direction: str) -> str:
    party = r["Customer" if direction == "ar" else "Payee"]
    company = await _company_id(db, party)
    consultant = None if company else await _consultant_id(db, party)
    if not company and not consultant:
        raise ValueError(f"{party} must exist as a company or consultant")
    result = await db.val(
        """insert into invoices (tenant_id, number, direction, company_id, consultant_id, sow_id, period_start, period_end,
                                 hours, rate, amount, issued_on, due_on, terms, status)
           values (:t, :n, :dir, :co, :con, (select id from sows where code = :sow), :ps, :pe, :h, :r, :a, :iss, :due, :terms,
                   :status)
           on conflict (tenant_id, number) do update set amount = excluded.amount, due_on = excluded.due_on
           returning (xmax = 0)""",
        {"t": tenant, "n": r["Invoice number"], "dir": direction, "co": company, "con": consultant, "sow": r.get("SOW ID") or None,
         "ps": _date(r.get("Period start")), "pe": _date(r.get("Period end")), "h": _num(r.get("Hours")) or 0,
         "r": _num(r.get("Rate")) or 0, "a": _num(r["Amount"]), "iss": _date(r.get("Issued")) or date.today(),
         "due": _date(r.get("Due date")), "terms": r.get("Terms") or None,
         "status": "sent" if direction == "ar" else "received"},
    )
    paid = _num(r.get("Already paid"))
    if paid:
        await db.run("""insert into payments (tenant_id, invoice_id, amount, paid_on, method, reference)
                        select :t, id, :a, coalesce(:d, current_date), 'Other', 'Imported' from invoices where number = :n
                        and not exists (select 1 from payments p where p.invoice_id = invoices.id and p.reference = 'Imported')""",
                     {"t": tenant, "a": paid, "d": _date(r.get("Paid date")), "n": r["Invoice number"]})
    return "created" if result else "updated"


async def import_ar_invoice(db: Db, tenant: Any, r: dict[str, str]) -> str:
    return await import_invoice(db, tenant, r, "ar")


async def import_ap_invoice(db: Db, tenant: Any, r: dict[str, str]) -> str:
    return await import_invoice(db, tenant, r, "ap")


async def import_tracked_document(db: Db, tenant: Any, r: dict[str, str]) -> str:
    company = await _company_id(db, r["Person or company"])
    consultant = None if company else await _consultant_id(db, r["Person or company"])
    if not company and not consultant:
        raise ValueError("Person or company not found")
    await db.run("""insert into tracked_documents (tenant_id, consultant_id, company_id, doc_type, label, expires_on, recipients)
                    values (:t, :con, :co, :type, :label, :exp, string_to_array(:to, ';'))""",
                 {"t": tenant, "con": consultant, "co": company, "type": r["Document type"].lower(), "label": r["Label"],
                  "exp": _date(r.get("Expires on")), "to": r.get("Email recipients (; separated)") or ""})
    return "created"


async def import_user(db: Db, tenant: Any, r: dict[str, str]) -> str:
    result = await db.val(
        """insert into memberships (tenant_id, invited_email, role, title, status)
           values (:t, :e, :role, :title, 'invited')
           on conflict (tenant_id, invited_email) where user_id is null do update set role = excluded.role
           returning (xmax = 0)""",
        {"t": tenant, "e": r["Email"], "role": r["Role"].lower().replace(" ", "_"), "title": r.get("Title") or None},
    )
    return "created" if result else "updated"


async def import_payroll(db: Db, tenant: Any, r: dict[str, str]) -> str:
    consultant = await _consultant_id(db, r["Employee (email or name)"])
    if not consultant:
        raise ValueError("Employee not found")
    exists = await db.val(
        "select id from payroll_lines where consultant_id = :c and pay_date = :d and period_start = :s",
        {"c": consultant, "d": _date(r["Pay date"]), "s": _date(r["Period start"])})
    params = {"t": tenant, "c": consultant, "s": _date(r["Period start"]), "e": _date(r["Period end"]), "d": _date(r["Pay date"]),
              "h": _num(r.get("Hours")), "g": _num(r["Gross pay"]), "tax": _num(r.get("Employer taxes")) or 0,
              "ben": _num(r.get("Benefits")) or 0, "net": _num(r.get("Net pay")), "id": exists}
    if exists:
        await db.run("""update payroll_lines set period_end = :e, hours = :h, gross = :g, employer_taxes = :tax, benefits = :ben,
                        net = :net where id = :id""", params)
        return "updated"
    await db.run("""insert into payroll_lines (tenant_id, consultant_id, period_start, period_end, pay_date, hours, gross,
                                               employer_taxes, benefits, net, source)
                    values (:t, :c, :s, :e, :d, :h, :g, :tax, :ben, :net, 'import')""", params)
    return "created"


# ----------------------------------------------------------------------------- registry
TEMPLATES: dict[str, Template] = {}


def _register(t: Template) -> None:
    TEMPLATES[t.key] = t


_register(Template("companies", "Clients & vendors (active and inactive)", [
    Column("Business ID", False, "text"), Column("Legal name", True),
    Column("Type", True, "choice", ("Client", "Prime vendor", "Vendor", "End client")),
    Column("EIN"), Column("State"), Column("Contact name"), Column("Contact email", False, "email"),
    Column("Default payment terms"), Column("Existing MSA ID"), Column("MSA effective date", kind="date"),
    Column("MSA expiry date", kind="date"), Column("Status", kind="choice", choices=("Active", "Inactive")),
    Column("Inactive since", kind="date"), Column("Inactive reason")],
    [["C-0001", "Nova Analytics Inc.", "Client", "XX-XXX7781", "MA", "R. Hughes", "ap@nova.example", "Net 30", "MSA-NOVA-01",
      "2026-11-01", "2028-10-31", "Active", "", ""],
     ["C-0002", "Pinewood Tech LLC", "Vendor", "XX-XXX2264", "NC", "G. Ellis", "ap@pinewood.example", "Net 30", "MSA-PW-01",
      "2023-01-01", "2025-12-31", "Inactive", "2025-12-31", "No active placements"]],
    import_company, ("tenant_admin", "finance", "account_manager", "legal")))

_register(Template("consultants", "Consultants (current, onboarding and former)", [
    Column("Consultant ID"), Column("Full name", True), Column("Email", True, "email"), Column("Mobile"),
    Column("Engagement type", True, "choice", ("W-2 full-time", "W-2 contract", "C2C", "E2E", "1099")),
    Column("Employer (C2C only)"), Column("Job title"), Column("Start date", True, "date"), Column("Work location"),
    Column("Status", kind="choice", choices=("Onboarding", "Active", "Former")), Column("End date (former only)", kind="date"),
    Column("Reason for leaving"), Column("Eligible for rehire (Y/N)", kind="bool")],
    [["", "Kavya Rao", "kavya.rao@example.com", "+1 555 010 2030", "W-2 full-time", "", "SAP FICO Consultant", "2026-10-26",
      "McKinney, TX", "Onboarding", "", "", ""],
     ["U000042", "Sanjay Mehta", "sanjay.m@example.com", "", "W-2 contract", "", "SAP SD Consultant", "2024-06-03", "Plano, TX",
      "Former", "2026-05-15", "Resigned - relocated", "Y"]],
    import_consultant, ("tenant_admin", "hr", "account_manager")))

_register(Template("projects", "Projects", [
    Column("Project code", True), Column("Project name", True), Column("Client"), Column("Prime vendor (if any)"),
    Column("Start date", kind="date"), Column("End date", kind="date"), Column("Client timesheet approver"), Column("Description")],
    [["PRJ-05", "Data Migration", "Atlas Foods Corp.", "", "2026-11-01", "2027-04-30", "J. Brooks", "Legacy ERP data migration"]],
    import_project, ("tenant_admin", "account_manager")))

_register(Template("agreements", "MSAs and contractor agreements (signed elsewhere)", [
    Column("Agreement ID", True), Column("Type", True, "choice", ("MSA", "Subcontractor agreement",
                                                                    "Independent contractor agreement (1099)", "NDA", "Offer letter")),
    Column("Counterparty", True), Column("Tenant is (Supplier / Buyer)", kind="choice", choices=("Supplier", "Buyer", "Employer")),
    Column("Effective date", True, "date"), Column("Expiry date", True, "date"), Column("Payment terms"), Column("Renewal"),
    Column("Notice period"), Column("Insurance required")],
    [["MSA-NOVA-01", "MSA", "Nova Analytics Inc.", "Supplier", "2026-11-01", "2028-10-31", "Net 30", "Auto, 1 year", "60 days",
      "GL $1M, E&O $2M"]],
    import_agreement, ("tenant_admin", "legal")))

_register(Template("sows", "SOWs and work orders (signed elsewhere)", [
    Column("SOW ID", True), Column("Agreement ID", True), Column("Side (We bill / We pay)", True, "choice", ("We bill", "We pay")),
    Column("Title"), Column("Start date", True, "date"), Column("End date", True, "date"), Column("Value (ceiling)", kind="number"),
    Column("Invoiced before myTrakIn", kind="number"), Column("Collected or paid before myTrakIn", kind="number")],
    [["SOW-AF-0101", "MSA-AF-ESG", "We bill", "Supplier Portal phase 2", "2027-03-01", "2027-08-31", "96000", "0", "0"]],
    import_sow, ("tenant_admin", "legal", "account_manager")))

_register(Template("placements", "Placements and rates (AR and AP only)", [
    Column("Consultant (email or name)", True), Column("Project code", True), Column("Role"), Column("Start date", True, "date"),
    Column("End date", kind="date"), Column("Hours per week", kind="number"), Column("AR customer (who we bill)", True),
    Column("AR SOW ID"), Column("AR bill rate", True, "number"), Column("AR terms"), Column("AP payee (vendor or 1099 name)"),
    Column("AP SOW ID"), Column("AP pay rate", kind="number"), Column("AP terms"), Column("Pay when paid (Y/N)", kind="bool")],
    [["ravi.kumar@example.com", "PRJ-02", "SAP Security Advisor", "2026-08-03", "2026-12-18", "16", "Atlas Foods Corp.",
      "SOW-AF-0091", "105", "Net 30", "BrightPath Tech LLC", "SOW-ESG-BP-019", "82", "Net 30", "N"]],
    import_placement, ("tenant_admin", "account_manager", "finance")))

_register(Template("ar_invoices", "Client invoices (AR) incl. history", [
    Column("Invoice number", True), Column("Customer", True), Column("SOW ID"), Column("Period start", kind="date"),
    Column("Period end", kind="date"), Column("Hours", kind="number"), Column("Rate", kind="number"),
    Column("Amount", True, "number"), Column("Issued", kind="date"), Column("Due date", kind="date"), Column("Terms"),
    Column("Already paid", kind="number"), Column("Paid date", kind="date")],
    [["ESG-AR-2026-0300", "Atlas Foods Corp.", "SOW-AF-0087", "2026-06-01", "2026-06-30", "168", "120", "20160",
      "2026-07-01", "2026-07-31", "Net 30", "20160", "2026-07-29"]],
    import_ar_invoice, ("tenant_admin", "finance")))

_register(Template("ap_invoices", "Vendor & 1099 invoices (AP) incl. old vendor payments", [
    Column("Invoice number", True), Column("Payee", True), Column("SOW ID"), Column("Period start", kind="date"),
    Column("Period end", kind="date"), Column("Hours", kind="number"), Column("Rate", kind="number"),
    Column("Amount", True, "number"), Column("Issued", kind="date"), Column("Due date", kind="date"), Column("Terms"),
    Column("Already paid", kind="number"), Column("Paid date", kind="date")],
    [["BP-INV-0874", "BrightPath Tech LLC", "SOW-ESG-BP-014", "2026-01-01", "2026-01-31", "167.2", "80", "13376",
      "2026-02-02", "2026-03-04", "Pay-when-paid", "13376", "2026-03-04"]],
    import_ap_invoice, ("tenant_admin", "finance")))

_register(Template("tracked_documents", "Expiring documents (I-9, passport, EAD, COI ...)", [
    Column("Person or company", True), Column("Document type", True, "choice",
                                               ("i9_reverification", "passport", "ead", "i94", "visa_notice", "coi", "w9",
                                                "background_check", "certification", "drivers_license", "agreement", "other")),
    Column("Label", True), Column("Expires on", kind="date"), Column("Email recipients (; separated)")],
    [["Anita Desai", "i9_reverification", "Form I-9 reverification (H-1B)", "2026-11-20", "anita@example.com;hr@example.com"]],
    import_tracked_document, ("tenant_admin", "hr", "legal")))

_register(Template("users", "Users to invite", [
    Column("Email", True, "email"), Column("Role", True, "choice", ("tenant_admin", "finance", "account_manager", "legal", "hr",
                                                                      "approver", "viewer")),
    Column("Title")],
    [["j.lopez@example.com", "finance", "AP specialist"]],
    import_user, ("tenant_admin",)))

_register(Template("payroll", "W-2 payroll results (from ADP, Gusto, Paychex ...)", [
    Column("Employee (email or name)", True), Column("Period start", True, "date"), Column("Period end", True, "date"),
    Column("Pay date", True, "date"), Column("Hours", kind="number"), Column("Gross pay", True, "number"),
    Column("Employer taxes", kind="number"), Column("Benefits", kind="number"), Column("Net pay", kind="number")],
    [["anita.desai@example.com", "2026-09-01", "2026-09-15", "2026-09-20", "88", "4800", "367.20", "310", "3520.55"]],
    import_payroll, ("tenant_admin", "finance")))
