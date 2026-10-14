"""Clients, prime vendors, vendors and end clients — now with company onboarding:
Business IDs, W-9 upload + extraction, domain verification, verification-gated
activation, and company-scoped members (owner/admin/member)."""

from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
from datetime import UTC, date, datetime
from uuid import UUID

import orjson
from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError

from ..deps import TenantDb, tenant_db
from ..errors import ApiError, bad_request, conflict, forbidden, not_found
from ..services import storage
from ..services import w9 as w9svc

router = APIRouter(prefix="/companies", tags=["companies"])

KINDS = "^(client|prime_vendor|vendor|end_client)$"
COMPANY_ROLES = "^(owner|admin|member)$"
DOMAIN_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))*\.[a-z]{2,}$")
W9_STATUSES = ("draft", "submitted", "under_review", "verified", "rejected")

TAX_PRIVILEGED_FINANCE = ("finance", "legal")   # ctx.allows() adds tenant_admin/system automatically


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
    domain: str | None = Field(None, max_length=253)
    business_type: str | None = Field(None, max_length=120)
    dba: str | None = Field(None, max_length=200)


class CompanyPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    kind: str | None = None
    ein: str | None = None
    state: str | None = None
    address: str | None = None
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    default_terms: str | None = None
    notes: str | None = None
    domain: str | None = Field(None, max_length=253)
    business_type: str | None = Field(None, max_length=120)
    dba: str | None = Field(None, max_length=200)
    onboarding_stage: int | None = Field(None, ge=0, le=8)


class StatusChange(BaseModel):
    status: str = Field(pattern="^(active|inactive)$")
    reason: str | None = Field(None, max_length=300)
    since: date | None = None


def _normalize_domain(raw: str | None) -> str | None:
    if not raw:
        return None
    domain = raw.strip().lower().removeprefix("http://").removeprefix("https://").removeprefix("www.").rstrip("/")
    if not DOMAIN_RE.match(domain):
        raise bad_request(f"'{raw.strip()}' doesn't look like a company domain (example: acme.com)")
    return domain


def _mask_tin(tin: str | None) -> str | None:
    """Show only the last 4 digits; separators stay so the shape is recognizable."""
    if not tin:
        return None
    digits = re.sub(r"\D", "", tin)
    tail = digits[-4:]
    masked = re.sub(r"\d", "•", tin[: len(tin) - len(tail)]) if len(tin) > len(tail) else ""
    return masked + tail


async def _tax_privileged(db: TenantDb, company_id: UUID) -> bool:
    """Finance/legal (+ tenant admin) and the company's own owner/admin see full tax data."""
    if db.ctx.allows(*TAX_PRIVILEGED_FINANCE):
        return True
    if db.ctx.company_id == company_id and db.ctx.role in ("vendor_admin", "client_user"):
        return True
    role = await db.val("select mytrakin.company_role(:c)", {"c": company_id})
    return role in ("owner", "admin")


def _shield(company: dict, privileged: bool) -> dict:
    if not privileged:
        company["ein"] = None
        company["tin"] = _mask_tin(company.get("tin"))
        company["w9_data"] = {}
        company["w9_note"] = None
    return company


async def _assign_business_code(db: TenantDb) -> str:
    for _ in range(5):
        n = await db.val("select mytrakin.next_number(:t, 'company')", {"t": db.ctx.tenant_id})
        code = f"C-{n:04d}"
        if await db.val("select 1 from companies where tenant_id = :t and business_code = :c",
                        {"t": db.ctx.tenant_id, "c": code}) is None:
            return code
    raise bad_request("Couldn't assign a Business ID — try again")


@router.get("")
async def list_companies(db: TenantDb = Depends(tenant_db), kind: str | None = None, status: str | None = None):
    show_money = db.ctx.allows("finance")
    rows = await db.all(
        """select c.id, c.business_code, c.name, c.kind, c.state, c.status, c.domain, c.w9_status,
                  c.contact_name, c.contact_email, c.default_terms,
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
    """Start onboarding: any workspace member can draft a company — it gets its Business ID
    and the creator becomes its owner. Activation stays staff-only through /activate."""
    code = await _assign_business_code(db)
    try:
        async with db.conn.begin_nested():
            company = await db.one(
                """insert into companies (tenant_id, business_code, name, kind, ein, state, address, contact_name, contact_email,
                                          contact_phone, default_terms, notes, domain, business_type, dba,
                                          status, onboarding_stage, created_by)
                   values (:t, :code, :name, :kind, :ein, upper(:state), :address, :cn, :ce, :cp, :terms, :notes,
                           :domain, :btype, :dba, 'onboarding', 1, :u)
                   returning *""",
                {"t": db.ctx.tenant_id, "code": code, "name": body.name.strip(), "kind": body.kind, "ein": body.ein,
                 "state": body.state, "address": body.address, "cn": body.contact_name, "ce": body.contact_email,
                 "cp": body.contact_phone, "terms": body.default_terms, "notes": body.notes,
                 "domain": _normalize_domain(body.domain), "btype": body.business_type, "dba": body.dba,
                 "u": db.ctx.user_id})
    except IntegrityError as exc:
        raise conflict(f"A company named '{body.name.strip()}' already exists") from exc
    # The companies_owner trigger crowns created_by as owner (a WITH CHECK
    # subquery could never see the membership row being inserted).
    return _shield(company, True)


@router.get("/{company_id}")
async def get_company(company_id: UUID, db: TenantDb = Depends(tenant_db)):
    company = await db.one("select * from companies where id = :id", {"id": company_id})
    if company is None:
        raise not_found("Company")
    privileged = await _tax_privileged(db, company_id)
    if not db.ctx.allows("finance"):
        company["ein"] = None
    company["logo_url"] = storage.public_url("avatars", company["logo_path"]) if company.get("logo_path") else None
    company["my_company_role"] = await db.val("select mytrakin.company_role(:c)", {"c": company_id})
    company["members"] = await db.all(
        """select cm.id, cm.company_role, cm.title, cm.status, coalesce(p.full_name, cm.invited_email::text) as name,
                  coalesce(p.email, cm.invited_email) as email
             from company_members cm left join profiles p on p.id = cm.user_id
            where cm.company_id = :id and cm.status <> 'removed' order by cm.company_role, name""",
        {"id": company_id}) if (privileged or company["my_company_role"]) else []
    _shield(company, privileged)
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
    if "domain" in fields:
        fields["domain"] = _normalize_domain(fields["domain"])
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    try:
        async with db.conn.begin_nested():
            row = await db.one(f"update companies set {sets} where id = :id returning *", {**fields, "id": company_id})
    except IntegrityError as exc:
        raise conflict("Another company already uses that name") from exc
    if row is None:
        raise not_found("Company")
    return _shield(row, await _tax_privileged(db, company_id))


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


# ============================================================================ onboarding
LOGO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_LOGO_BYTES = 2 * 1024 * 1024
MAX_W9_BYTES = 4 * 1024 * 1024


async def _company_or_404(db: TenantDb, company_id: UUID) -> dict:
    company = await db.one("select * from companies where id = :id", {"id": company_id})
    if company is None:
        raise not_found("Company")
    return company


def _can_manage_company(db: TenantDb, company_id: UUID, role: str | None) -> bool:
    return db.ctx.allows("tenant_admin") or role in ("owner", "admin")


@router.post("/{company_id}/logo")
async def upload_logo(company_id: UUID, file: UploadFile = File(), db: TenantDb = Depends(tenant_db)):
    """Company logo (JPEG, PNG or WebP, up to 2 MB). Shown on the company profile."""
    await _company_or_404(db, company_id)
    role = await db.val("select mytrakin.company_role(:c)", {"c": company_id})
    if not (db.ctx.allows("account_manager", "finance", "legal") or role in ("owner", "admin")):
        raise forbidden()
    ext = LOGO_TYPES.get(file.content_type or "")
    if ext is None:
        raise bad_request("Use a JPEG, PNG or WebP image")
    data = await file.read()
    if len(data) > MAX_LOGO_BYTES:
        raise bad_request("The logo is larger than 2 MB")
    path = f"company/{company_id}/logo-{secrets.token_hex(8)}.{ext}"
    await storage.upload("avatars", path, data, file.content_type or "image/jpeg", upsert=True)
    await db.run("update companies set logo_path = :p where id = :id", {"p": path, "id": company_id})
    return {"logo_url": storage.public_url("avatars", path)}


@router.post("/{company_id}/w9")
async def upload_w9(company_id: UUID, file: UploadFile = File(), db: TenantDb = Depends(tenant_db)):
    """Upload a W-9: the document is stored, its fields are extracted (digital text,
    otherwise OCR when available) and returned for review. Nothing is trusted until
    staff verify it — the company stays non-active meanwhile."""
    company = await _company_or_404(db, company_id)
    role = await db.val("select mytrakin.company_role(:c)", {"c": company_id})
    if not (db.ctx.allows("account_manager", "finance", "legal", "hr") or role in ("owner", "admin")):
        raise forbidden()
    if (file.content_type or "") not in {"application/pdf", "image/jpeg", "image/png", "image/webp"}:
        raise bad_request("Upload the W-9 as a PDF, JPEG, PNG or WebP file")
    data = await file.read()
    if len(data) > MAX_W9_BYTES:
        raise bad_request("The file is larger than 4 MB")
    if file.content_type == "application/pdf" and not data.startswith(b"%PDF"):
        raise bad_request("That file isn't a valid PDF")

    parsed = await w9svc.extract_w9(data, file.content_type or "application/pdf")
    ext = "pdf" if file.content_type == "application/pdf" else {"image/jpeg": "jpg", "image/png": "png"}.get(file.content_type or "", "webp")
    doc_path = f"{company['tenant_id']}/company/{company_id}/w9-{secrets.token_hex(6)}.{ext}"
    await storage.upload("documents", doc_path, data, file.content_type or "application/octet-stream")
    doc = await db.one(
        """insert into documents (tenant_id, owner_type, owner_id, name, storage_path, mime_type, size_bytes, sha256)
           values (:t, 'company', :o, :n, :p, :m, :s, :h) returning id""",
        {"t": company["tenant_id"], "o": company_id, "n": file.filename or f"W-9.{ext}", "p": doc_path,
         "m": file.content_type, "s": len(data), "h": hashlib.sha256(data).hexdigest()})
    w9_fields = {k: parsed.get(k) for k in ("legal_name", "dba", "tax_classification", "tin", "tin_type",
                                            "address", "city", "state", "zip")}
    await db.run(
        """update companies set w9_data = cast(:d as jsonb), w9_status = 'submitted', w9_document_id = :doc,
                  w9_decided_at = null, w9_decided_by = null, w9_note = null
            where id = :id""",
        {"d": orjson.dumps(w9_fields).decode(), "doc": doc["id"], "id": company_id})
    await db.run(
        """insert into tracked_documents (tenant_id, company_id, doc_type, label, status)
           values (:t, :c, 'w9', 'Form W-9', 'valid')
           on conflict do nothing""",
        {"t": company["tenant_id"], "c": company_id})
    return {"extraction": {**parsed, "document_id": doc["id"]}, "w9_status": "submitted"}


class TaxIn(BaseModel):
    dba: str | None = Field(None, max_length=200)
    tax_classification: str | None = Field(None, max_length=120)
    tin: str | None = Field(None, max_length=20)
    tin_type: str | None = Field(None, pattern="^(ein|ssn)$")
    tax_address: str | None = None
    ein: str | None = Field(None, max_length=20)


class W9Decision(BaseModel):
    decision: str = Field(pattern="^(verified|rejected)$")
    note: str | None = Field(None, max_length=1000)


@router.patch("/{company_id}/tax")
async def update_tax(company_id: UUID, body: TaxIn, db: TenantDb = Depends(tenant_db)):
    """Correct the W-9 / tax details after reviewing the extraction. TIN is stored
    digits-and-dashes only; only privileged roles ever read it back."""
    await _company_or_404(db, company_id)
    role = await db.val("select mytrakin.company_role(:c)", {"c": company_id})
    if not (db.ctx.allows("finance", "legal") or role in ("owner", "admin")):
        raise forbidden()
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise bad_request("Nothing to change")
    if "tin" in fields and fields["tin"]:
        digits = re.sub(r"\D", "", fields["tin"])
        if len(digits) != 9:
            raise bad_request("The TIN must have 9 digits (EIN XX-XXXXXXX or SSN XXX-XX-XXXX)")
        fields["tin"] = (f"{digits[:3]}-{digits[3:5]}-{digits[5:]}" if fields.get("tin_type") == "ssn"
                         else f"{digits[:2]}-{digits[2:]}")
    fields.pop("tin_type", None)   # only shapes the format above, not a column
    if not fields:
        raise bad_request("Nothing to change")
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    row = await db.one(f"update companies set {sets} where id = :id returning *", {**fields, "id": company_id})
    return _shield(row, True)


@router.post("/{company_id}/w9/decision")
async def decide_w9(company_id: UUID, body: W9Decision, db: TenantDb = Depends(tenant_db)):
    """Staff review the submitted W-9 against the attached document."""
    await _company_or_404(db, company_id)
    db.ctx.require("finance", "legal")
    if body.decision == "rejected" and not body.note:
        raise bad_request("Say what's wrong so it can be fixed and resubmitted")
    row = await db.one(
        """update companies set w9_status = :s, w9_decided_at = now(), w9_decided_by = :u, w9_note = :n
            where id = :id returning w9_status""",
        {"s": body.decision, "u": db.ctx.user_id, "n": body.note, "id": company_id})
    return {"w9_status": row["w9_status"]}


def _email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.split("@", 1)[1].lower()


async def _run_verification(db: TenantDb, company: dict) -> dict:
    """Recompute every check fresh and store the result. Returns {checks, blockers}."""
    checks: dict[str, dict] = {}
    blockers: list[str] = []

    missing = [label for label, present in
               (("legal name", company["name"]), ("domain", company.get("domain")),
                ("business address", company.get("address")), ("contact e-mail", company.get("contact_email")))
               if not present]
    checks["required_fields"] = {"status": "pass" if not missing else "fail",
                                 "detail": "All required details are present" if not missing else f"Missing: {', '.join(missing)}"}
    if missing:
        blockers.append(f"Complete the company details ({', '.join(missing)})")

    domain, email_domain = company.get("domain"), _email_domain(company.get("contact_email"))
    if domain and email_domain:
        ok = email_domain == domain or email_domain.endswith(f".{domain}")
        checks["domain"] = {"status": "pass" if ok else "fail",
                            "detail": f"Contact e-mail is on {email_domain}" if ok
                            else f"Contact e-mail ({email_domain}) is not on {domain}"}
        if not ok:
            blockers.append("Contact e-mail must be on the company domain")
    else:
        checks["domain"] = {"status": "fail", "detail": "Company domain and contact e-mail are both required"}
        blockers.append("Add the company domain and a contact e-mail on it")
    if domain:
        checks["mx"] = await _check_mx(domain)

    tin_digits = re.sub(r"\D", "", company.get("tin") or "")
    w9_tin_digits = re.sub(r"\D", "", (company.get("w9_data") or {}).get("tin") or "")
    if company.get("w9_status") == "verified":
        checks["w9"] = {"status": "pass", "detail": "W-9 verified by staff"}
    else:
        checks["w9"] = {"status": "fail", "detail": f"W-9 is {company.get('w9_status', 'draft')} — upload it and have staff verify"}
        blockers.append("Verify the W-9 (upload, review, staff approval)")
    if tin_digits and w9_tin_digits:
        same = tin_digits == w9_tin_digits
        checks["tin_match"] = {"status": "pass" if same else "fail",
                               "detail": "TIN matches the W-9" if same else "TIN doesn't match the W-9 extraction"}
        if not same:
            blockers.append("Fix the TIN so it matches the W-9")
    elif tin_digits or w9_tin_digits:
        checks["tin_match"] = {"status": "fail", "detail": "TIN is needed both on the company and the W-9"}
        blockers.append("Enter the TIN so it can be matched with the W-9")

    owner = await db.val(
        """select coalesce(p.full_name, cm.invited_email::text) from company_members cm
             left join profiles p on p.id = cm.user_id
            where cm.company_id = :c and cm.company_role = 'owner' and cm.status = 'active'
            order by cm.created_at limit 1""", {"c": company["id"]})
    checks["owner"] = {"status": "pass" if owner else "fail",
                       "detail": f"Owner: {owner}" if owner else "No active owner assigned"}
    if not owner:
        blockers.append("Assign a company owner")

    checks["checked_at"] = datetime.now(UTC).isoformat()
    await db.run("update companies set verification = cast(:v as jsonb) where id = :id",
                 {"v": orjson.dumps(checks).decode(), "id": company["id"]})
    return {"checks": checks, "blockers": blockers}


async def _check_mx(domain: str) -> dict:
    """Advisory only: a missing mail server doesn't block activation."""
    try:
        import dns.resolver

        def _lookup() -> bool:
            resolver = dns.resolver.Resolver()
            resolver.lifetime = 5
            try:
                return len(list(resolver.resolve(domain, "MX"))) > 0
            except Exception:
                return False

        has_mx = await asyncio.to_thread(_lookup)
        return {"status": "pass" if has_mx else "warn",
                "detail": "Mail server found" if has_mx else "No mail server found — codes to this domain may not deliver"}
    except Exception:
        return {"status": "warn", "detail": "Mail check skipped"}


@router.post("/{company_id}/verify")
async def verify_company(company_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Re-run the verification checks without activating. Shows what still blocks."""
    company = await _company_or_404(db, company_id)
    role = await db.val("select mytrakin.company_role(:c)", {"c": company_id})
    if not (db.ctx.internal or role in ("owner", "admin")):
        raise forbidden()
    return await _run_verification(db, company)


@router.post("/{company_id}/activate")
async def activate_company(company_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Activate the company. Strict: every gate must pass — no override."""
    company = await _company_or_404(db, company_id)
    db.ctx.require("account_manager", "finance", "legal")
    if company["status"] == "active":
        return {"status": "active", "business_code": company["business_code"]}
    result = await _run_verification(db, company)
    if result["blockers"]:
        raise ApiError(422, "verification_failed",
                       "The company can't be activated yet: " + "; ".join(result["blockers"]))
    row = await db.one(
        """update companies set status = 'active', onboarding_stage = 8, verified_at = now()
            where id = :id returning status, business_code""", {"id": company_id})
    return {**row, "checks": result["checks"]}


# ============================================================================ members
class MemberIn(BaseModel):
    email: EmailStr
    company_role: str = Field(pattern=COMPANY_ROLES)
    title: str | None = None


class MemberPatch(BaseModel):
    company_role: str | None = Field(None, pattern=COMPANY_ROLES)
    status: str | None = Field(None, pattern="^(active|removed)$")


async def _active_owners(db: TenantDb, company_id: UUID, exclude: UUID | None = None) -> int:
    return await db.val(
        """select count(*) from company_members
            where company_id = :c and company_role = 'owner' and status = 'active'
              and (cast(:x as uuid) is null or id <> :x)""", {"c": company_id, "x": exclude})


@router.get("/{company_id}/members")
async def list_members(company_id: UUID, db: TenantDb = Depends(tenant_db)):
    await _company_or_404(db, company_id)
    role = await db.val("select mytrakin.company_role(:c)", {"c": company_id})
    if not (db.ctx.internal or role):
        raise forbidden()
    return await db.all(
        """select cm.id, cm.company_role, cm.title, cm.status, cm.created_at,
                  coalesce(p.full_name, cm.invited_email::text) as name,
                  coalesce(p.email, cm.invited_email) as email, uc.code as user_code
             from company_members cm left join profiles p on p.id = cm.user_id
             left join user_codes uc on uc.user_id = cm.user_id
            where cm.company_id = :id and cm.status <> 'removed'
            order by cm.company_role, name""", {"id": company_id})


@router.post("/{company_id}/members", status_code=201)
async def add_member(company_id: UUID, body: MemberIn, db: TenantDb = Depends(tenant_db)):
    """Invite someone to the company. They claim it automatically at first sign-in."""
    await _company_or_404(db, company_id)
    role = await db.val("select mytrakin.company_role(:c)", {"c": company_id})
    if not _can_manage_company(db, company_id, role):
        raise forbidden()
    existing = await db.val("select id from profiles where email = :e", {"e": body.email})
    try:
        async with db.conn.begin_nested():
            row = await db.one(
                """insert into company_members (tenant_id, company_id, user_id, invited_email, company_role, title, status)
                   values (:t, :c, :u, :e, :r, :title, :status)
                   on conflict (company_id, invited_email) where user_id is null
                   do update set company_role = excluded.company_role, title = excluded.title
                   returning id, status""",
                {"t": db.ctx.tenant_id, "c": company_id, "u": existing,
                 "e": None if existing else body.email, "r": body.company_role, "title": body.title,
                 "status": "active" if existing else "invited"})
    except IntegrityError as exc:
        raise conflict("This person is already a member of this company") from exc
    return row


@router.patch("/{company_id}/members/{member_id}")
async def update_member(company_id: UUID, member_id: UUID, body: MemberPatch, db: TenantDb = Depends(tenant_db)):
    await _company_or_404(db, company_id)
    role = await db.val("select mytrakin.company_role(:c)", {"c": company_id})
    if not _can_manage_company(db, company_id, role):
        raise forbidden()
    target = await db.one("select company_role, status from company_members where id = :m and company_id = :c",
                          {"m": member_id, "c": company_id})
    if target is None:
        raise not_found("Member")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise bad_request("Nothing to change")
    if (target["company_role"] == "owner" and (fields.get("company_role", "owner") != "owner"
                                               or fields.get("status", "active") != "active")
            and await _active_owners(db, company_id, exclude=member_id) < 1):
        raise bad_request("A company needs at least one active owner — assign another first")
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    return await db.one(f"update company_members set {sets} where id = :m returning *", {**fields, "m": member_id})


@router.delete("/{company_id}/members/{member_id}")
async def remove_member(company_id: UUID, member_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Remove someone from the company (history is kept). The last owner can't be removed."""
    await _company_or_404(db, company_id)
    role = await db.val("select mytrakin.company_role(:c)", {"c": company_id})
    if not _can_manage_company(db, company_id, role):
        raise forbidden()
    target = await db.one("select company_role from company_members where id = :m and company_id = :c",
                          {"m": member_id, "c": company_id})
    if target is None:
        raise not_found("Member")
    if target["company_role"] == "owner" and await _active_owners(db, company_id, exclude=member_id) < 1:
        raise bad_request("A company needs at least one active owner — assign another first")
    await db.run("update company_members set status = 'removed' where id = :m", {"m": member_id})
    return {"id": member_id, "removed": True}
