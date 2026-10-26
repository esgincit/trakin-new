"""Country-first business creation (US W-9 / India MOA + CIN).

The flow gates creation itself — nothing is created until every step passes:

    US: pick country → upload W-9 (parsed: legal name, business type, EIN,
        address, city, state, ZIP; EIN format + uniqueness checked) →
        domain + company e-mail + DBA → OTP to the company e-mail →
        authorization checkbox → company created, creator is Super Admin.
    IN: pick country → legal name, CIN (format + uniqueness), street, city,
        state, PIN + mandatory MOA upload (stored, not parsed in Phase 1) →
        domain + company e-mail + DBA → OTP → authorization → created.

E-mail OTP goes through the app's own mailer (Zoho/SMTP), never Supabase Auth,
so it works while Supabase's mailer is down. Codes are salted hashes with a
10-minute expiry and 5 attempts; resends are rate-limited to one per minute.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import orjson
from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import DBAPIError, IntegrityError

from ..config import get_settings
from ..deps import TenantDb, onboarding_db, tenant_db, user_db
from ..errors import ApiError, bad_request, conflict, forbidden, not_found
from ..services import storage
from ..services import w9 as w9svc
from ..services.email import render, send_email
from ..utils import client_ip, otp_code, sha256_hex
from .companies import COMPANY_KINDS, _assign_business_code, _normalize_domain, _roles

router = APIRouter(prefix="/onboarding", tags=["company onboarding"])

KINDS = "^(client|prime_vendor|vendor|end_client)$"
CIN_RE = re.compile(r"^[A-Z][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$")
PIN_RE = re.compile(r"^\d{6}$")
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
MAX_DOC_BYTES = 4 * 1024 * 1024
OTP_TTL_MINUTES = 10
OTP_RESEND_SECONDS = 60
OTP_MAX_ATTEMPTS = 5


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _norm_cin(raw: str | None) -> str:
    return re.sub(r"\s+", "", (raw or "").upper())


def _mask(email: str | None) -> str:
    name, _, domain = (email or "").partition("@")
    return f"{name[:2]}{'•' * max(1, len(name) - 2)}@{domain}" if domain else "—"


async def _session(db: TenantDb, session_id: UUID) -> dict:
    row = await db.one("select * from onboarding_sessions where id = :id", {"id": session_id})
    if row is None:
        raise not_found("Onboarding session")
    if row["created_by"] != db.ctx.user_id and not db.ctx.internal:
        raise forbidden()
    if row["status"] == "complete":
        raise bad_request("This onboarding is already complete")
    if row["expires_at"] < datetime.now(UTC):
        await db.run("update onboarding_sessions set status = 'expired' where id = :id", {"id": session_id})
        raise bad_request("This onboarding session expired — start a new one")
    return row


async def _ein_taken(db: TenantDb, digits: str) -> dict | None:
    """Another company in this workspace already registered this EIN (either column)."""
    if not digits:
        return None
    return await db.one(
        """select business_code, name from companies
            where tenant_id = :t
              and (regexp_replace(coalesce(tin, ''), '\\D', '', 'g') = :d
                   or regexp_replace(coalesce(ein, ''), '\\D', '', 'g') = :d)""",
        {"t": db.ctx.tenant_id, "d": digits})


async def _store_session_doc(db: TenantDb, session_id: UUID, label: str, filename: str,
                             content_type: str, data: bytes) -> dict:
    ext = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}.get(content_type, "webp")
    path = f"{db.ctx.tenant_id}/onboarding/{session_id}/{label.lower()}-{secrets.token_hex(6)}.{ext}"
    await storage.upload("documents", path, data, content_type)
    return await db.one(
        """insert into documents (tenant_id, owner_type, owner_id, name, storage_path, mime_type, size_bytes, sha256,
                                  uploaded_by)
           values (:t, 'session', :o, :n, :p, :m, :s, :h, :u) returning id, storage_path""",
        {"t": db.ctx.tenant_id, "o": session_id, "n": filename or f"{label}.{ext}", "p": path,
         "m": content_type, "s": len(data), "h": hashlib.sha256(data).hexdigest(), "u": db.ctx.user_id})


def _check_upload(file: UploadFile, label: str) -> str:
    content_type = file.content_type or "application/octet-stream"
    if content_type not in {"application/pdf", "image/jpeg", "image/png", "image/webp"}:
        raise bad_request(f"Upload the {label} as a PDF, JPEG, PNG or WebP file")
    return content_type


def _public_session(row: dict) -> dict:
    payload = row.get("payload") or {}
    return {"id": row["id"], "country": row["country"], "status": row["status"],
            "company_email": row.get("company_email"),
            "email_verified": row.get("email_verified_at") is not None,
            "details": payload.get("details", {}),
            "w9": {k: v for k, v in (payload.get("w9") or {}).items() if k != "document_id"},
            "w9_document_id": (payload.get("w9") or {}).get("document_id"),
            "has_moa": bool((payload.get("moa") or {}).get("document_id")),
            "expires_at": row.get("expires_at")}


class SessionIn(BaseModel):
    country: str = Field(pattern="^(US|IN)$")


@router.post("/sessions", status_code=201)
async def start_session(body: SessionIn, db: TenantDb = Depends(onboarding_db)):
    """Pick a country. Any workspace member can start; creation itself is gated."""
    row = await db.one(
        """insert into onboarding_sessions (tenant_id, country, created_by)
           values (:t, :c, :u) returning *""",
        {"t": db.ctx.tenant_id, "c": body.country, "u": db.ctx.user_id})
    return _public_session(row)


@router.post("/accounts", status_code=201)
async def start_account(body: SessionIn, db: TenantDb = Depends(user_db)):
    """Create my company: opens a new company (pending platform activation) with me as its
    owner and starts the wizard inside it. The web app then sends X-Tenant-Id = tenant_id."""
    try:
        async with db.conn.begin_nested():
            tid = await db.val("select mytrakin.start_company_account(:u)", {"u": db.ctx.user_id})
    except DBAPIError as exc:
        if "too_many_pending" in str(exc):
            raise ApiError(429, "too_many_pending",
                           "You already have 3 companies waiting — finish or wait for those first") from exc
        raise
    await db.run("select mytrakin.begin_request(:u, :t, 'tenant_admin', null, null, :ip, :ua)",
                 {"u": db.ctx.user_id, "t": tid, "ip": db.ctx.ip, "ua": db.ctx.user_agent})
    db.ctx.tenant_id = tid
    row = await db.one("insert into onboarding_sessions (tenant_id, country, created_by) values (:t, :c, :u) returning *",
                       {"t": tid, "c": body.country, "u": db.ctx.user_id})
    return {**_public_session(row), "tenant_id": tid}


@router.delete("/accounts/{tenant_id}")
async def discard_account(tenant_id: UUID, db: TenantDb = Depends(user_db)):
    """Throw away my own unfinished company draft (wizard closed before anything was
    submitted). Only drafts — no company profile yet — can be discarded; a submitted
    company waits for the platform decision. Frees a slot under the 3-pending cap."""
    gone = await db.val("select mytrakin.discard_company_account(:u, :t)",
                        {"u": db.ctx.user_id, "t": tenant_id})
    if not gone:
        raise not_found("Draft company")
    return {"id": tenant_id, "discarded": True}


@router.post("/resubmit")
async def resubmit_company(db: TenantDb = Depends(tenant_db)):
    """The owner of a rejected company fixed its details: send it back to the myTrakIn team (T011303-1084)."""
    if not db.ctx.is_owner:
        raise forbidden("Only the company's owner can resubmit it")
    row = await db.one("""update tenants set status = 'onboarding' where id = :t and status = 'rejected'
                           returning id, status""", {"t": db.ctx.tenant_id})
    if row is None:
        raise conflict("Only a rejected company can be resubmitted")
    return row


@router.get("/sessions")
async def my_sessions(db: TenantDb = Depends(onboarding_db)):
    """My unfinished onboardings, so a closed wizard can resume."""
    rows = await db.all(
        """select * from onboarding_sessions
            where created_by = :u and status <> 'complete' and expires_at > now()
            order by created_at desc""", {"u": db.ctx.user_id})
    return [_public_session(r) for r in rows]


@router.post("/sessions/{session_id}/w9")
async def upload_session_w9(session_id: UUID, file: UploadFile = File(), db: TenantDb = Depends(onboarding_db)):
    """US step 1: upload the W-9. Format, parsing and EIN uniqueness are validated
    before anything is accepted — the session stores the parsed result."""
    row = await _session(db, session_id)
    if row["country"] != "US":
        raise bad_request("W-9 upload applies to US businesses only")
    content_type = _check_upload(file, "W-9")
    data = await file.read()
    if len(data) > MAX_DOC_BYTES:
        raise bad_request("The file is larger than 4 MB")
    if content_type == "application/pdf" and not data.startswith(b"%PDF"):
        raise bad_request("That file isn't a valid PDF")
    parsed = await w9svc.extract_w9(data, content_type)
    if parsed.get("engine") == "none":
        raise ApiError(422, "w9_unreadable",
                       parsed.get("note") or "This W-9 couldn't be read. Upload a digital PDF or type the details manually.")
    if not parsed.get("legal_name") or not parsed.get("tin"):
        missing = [label for label, value in (("legal name", parsed.get("legal_name")),
                                              ("EIN/SSN", parsed.get("tin"))) if not value]
        found = [label for label, value in
                 (("business name", parsed.get("dba")), ("address", parsed.get("address")),
                  ("city", parsed.get("city")), ("classification", parsed.get("tax_classification"))) if value]
        raise ApiError(422, "w9_incomplete",
                       f"We read the W-9 but couldn't find the {' and '.join(missing)}."
                       + (f" Found: {', '.join(found)}." if found else "")
                       + " Upload a clearer copy or enter the details manually.")
    digits = _digits(parsed.get("tin"))
    if len(digits) != 9:
        raise ApiError(422, "w9_bad_tin", "The EIN on this W-9 doesn't have 9 digits")
    taken = await _ein_taken(db, digits)
    if taken:
        raise conflict(f"This EIN is already registered to {taken['name']} ({taken['business_code']})")
    doc = await _store_session_doc(db, session_id, "W-9", file.filename or "W-9",
                                   content_type, data)
    payload = row["payload"] or {}
    payload["w9"] = {**parsed, "document_id": str(doc["id"])}
    await db.run("update onboarding_sessions set payload = cast(:p as jsonb) where id = :id",
                 {"p": orjson.dumps(payload).decode(), "id": session_id})
    return {"parsed": parsed, "document_id": doc["id"]}


class DetailsIn(BaseModel):
    kind: str | None = Field(None, pattern=KINDS)
    kinds: list[str] | None = None   # every role the business plays; kind is the primary (first)
    step: int | None = Field(None, ge=1, le=4)   # wizard stage; step 1 saves MCA/W-9 data only
    domain: str | None = Field(None, max_length=253)
    company_email: EmailStr | None = None
    dba: str | None = Field(None, max_length=200)
    contact_name: str | None = Field(None, max_length=120)
    contact_phone: str | None = Field(None, max_length=40)
    # US: corrections to the parsed W-9 (or a fully manual entry when parsing failed).
    manual: bool = False
    legal_name: str | None = Field(None, min_length=2, max_length=200)
    business_type: str | None = Field(None, max_length=120)
    tin_type: str | None = Field(None, pattern="^(ein|ssn)$")
    ein: str | None = Field(None, max_length=20)
    address: str | None = None
    city: str | None = Field(None, max_length=120)
    state: str | None = Field(None, max_length=120)
    zip: str | None = Field(None, max_length=20)
    # India: manual entry (no parsing in Phase 1).
    cin: str | None = Field(None, max_length=25)
    street: str | None = None
    pin: str | None = Field(None, max_length=10)


@router.patch("/sessions/{session_id}")
async def save_details(session_id: UUID, body: DetailsIn, db: TenantDb = Depends(onboarding_db)):
    """Company details. US: domain/e-mail/DBA plus optional W-9 corrections.
    India: full manual entry with CIN format + uniqueness checks."""
    row = await _session(db, session_id)
    payload = row["payload"] or {}
    details = payload.get("details", {})
    errors: dict[str, str] = {}

    values = body.model_dump(exclude_unset=True)
    if "domain" in values:
        try:
            values["domain"] = _normalize_domain(values["domain"])
        except ApiError as exc:
            errors["domain"] = exc.message
    email = values.get("company_email") or details.get("company_email") or row.get("company_email")
    if not email and values.get("step") != 1:
        # Step 1 (MCA details / W-9 review) has no e-mail field by design —
        # e-mail becomes mandatory from step 2, and verified before creation.
        errors["company_email"] = "Company e-mail is required"
    details.update({k: v for k, v in values.items() if k in
                    ("kind", "kinds", "domain", "company_email", "dba", "contact_name", "contact_phone")})
    if "kinds" in details or "kind" in details:
        try:
            primary, roles = _roles(details.get("kind"), details.get("kinds"))
        except ApiError as exc:
            errors["kinds"] = exc.message
        else:
            details["kind"], details["kinds"] = primary, roles

    if row["country"] == "US":
        w9 = payload.get("w9")
        if not w9:
            if not values.get("manual"):
                raise bad_request("Upload the W-9 first — parsing comes before details")
            w9 = {"manual_entry": True}
        for key in ("legal_name", "business_type", "tin_type", "ein", "address", "city", "state", "zip"):
            if key in values and values[key]:
                w9[key] = values[key]
        ein_digits = _digits(w9.get("tin") or w9.get("ein"))
        if w9.get("ein"):
            ein_digits = _digits(w9["ein"])
            if len(ein_digits) != 9:
                errors["ein"] = "The EIN/SSN must have 9 digits"
        if not w9.get("legal_name"):
            errors["legal_name"] = "Legal name is required"
        if ein_digits and len(ein_digits) == 9:
            taken = await _ein_taken(db, ein_digits)
            if taken:
                errors["ein"] = f"This EIN is already registered to {taken['name']} ({taken['business_code']})"
        elif not errors.get("ein"):
            errors["ein"] = "EIN is required"
        payload["w9"] = w9
    else:
        for key in ("legal_name", "cin", "street", "city", "state", "pin"):
            if key in values and values[key]:
                details[key] = values[key]
        for key in ("legal_name", "street", "city", "state"):
            if not details.get(key):
                errors[key] = "This field is required"
        cin = _norm_cin(details.get("cin"))
        if not cin:
            errors["cin"] = "CIN is required"
        elif not CIN_RE.match(cin):
            errors["cin"] = "CIN must look like L12345MH2020PLC123456 (21 characters)"
        else:
            details["cin"] = cin
            dup = await db.val(
                "select business_code from companies where tenant_id = :t and cin = :c", {"t": db.ctx.tenant_id, "c": cin})
            if dup:
                errors["cin"] = f"This CIN is already registered to business {dup}"
        pin = (details.get("pin") or "").strip()
        if pin and not PIN_RE.match(pin):
            errors["pin"] = "PIN code must be 6 digits"
        elif not pin:
            errors["pin"] = "PIN code is required"
        state = (details.get("state") or "").strip()
        if state and len(state) > 100:
            errors["state"] = "State name is too long"

    if errors:
        raise ApiError(422, "invalid_details", "; ".join(f"{k}: {v}" for k, v in errors.items()))
    payload["details"] = details
    if email and email != row.get("company_email"):
        await db.run(
            """update onboarding_sessions
                  set payload = cast(:p as jsonb), company_email = :e, email_verified_at = null,
                      email_verified_for = null, email_otp_hash = null, status = 'draft'
                where id = :id""",
            {"p": orjson.dumps(payload).decode(), "e": email, "id": session_id})
    else:
        await db.run("update onboarding_sessions set payload = cast(:p as jsonb) where id = :id",
                     {"p": orjson.dumps(payload).decode(), "id": session_id})
    row = await db.one("select * from onboarding_sessions where id = :id", {"id": session_id})
    return _public_session(row)


@router.post("/sessions/{session_id}/moa")
async def upload_session_moa(session_id: UUID, file: UploadFile = File(), db: TenantDb = Depends(onboarding_db)):
    """India: the MOA is mandatory. Stored with the session (Phase 1: no parsing)."""
    row = await _session(db, session_id)
    if row["country"] != "IN":
        raise bad_request("MOA upload applies to Indian businesses only")
    content_type = _check_upload(file, "MOA")
    data = await file.read()
    if len(data) > MAX_DOC_BYTES:
        raise bad_request("The file is larger than 4 MB")
    if content_type == "application/pdf" and not data.startswith(b"%PDF"):
        raise bad_request("That file isn't a valid PDF")
    doc = await _store_session_doc(db, session_id, "MOA", file.filename or "MOA",
                                   content_type, data)
    payload = row["payload"] or {}
    payload["moa"] = {"document_id": str(doc["id"]), "name": file.filename or "MOA"}
    await db.run("update onboarding_sessions set payload = cast(:p as jsonb) where id = :id",
                 {"p": orjson.dumps(payload).decode(), "id": session_id})
    return {"document_id": doc["id"]}


@router.post("/sessions/{session_id}/email-code")
async def send_email_code(session_id: UUID, db: TenantDb = Depends(onboarding_db)):
    """E-mail a 6-digit code to the company e-mail (proves control of it)."""
    row = await _session(db, session_id)
    email = row.get("company_email")
    if not email:
        raise bad_request("Save the company e-mail first")
    now = datetime.now(UTC)
    if row.get("email_otp_sent_at") and row["email_otp_sent_at"] > now - timedelta(seconds=OTP_RESEND_SECONDS):
        raise ApiError(429, "too_soon", "A code was just sent. Wait a minute before asking for another.")
    code = otp_code()
    await db.run(
        """update onboarding_sessions
              set email_otp_code = :c, email_otp_hash = null, email_otp_expires = :exp,
                  email_otp_attempts = 0, email_otp_sent_at = :now
            where id = :id""",
        {"c": code, "exp": now + timedelta(minutes=OTP_TTL_MINUTES),
         "now": now, "id": session_id})
    await send_email(None, to=email, subject=f"Your verification code: {code}", kind="company_email_otp",
                     html_body=render("Verify this company e-mail",
                                      [f"Enter {code} to prove {email} belongs to your business.",
                                       f"The code expires in {OTP_TTL_MINUTES} minutes. If you didn't ask for it, ignore this e-mail."]),
                     tenant_id=db.ctx.tenant_id)
    result: dict = {"sent_to": _mask(email)}
    if get_settings().environment == "test":
        result["test_code"] = code   # CI only: no mailer runs there
    return result


class OtpIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


@router.post("/sessions/{session_id}/email-verify")
async def verify_email_code(session_id: UUID, body: OtpIn, db: TenantDb = Depends(onboarding_db)):
    row = await _session(db, session_id)
    now = datetime.now(UTC)
    has_code = bool(row.get("email_otp_code")) or bool(row.get("email_otp_hash"))
    if not has_code or not row.get("email_otp_expires") or row["email_otp_expires"] < now:
        raise bad_request("The code has expired. Ask for a new one.", "code_expired")
    if (row.get("email_otp_attempts") or 0) >= OTP_MAX_ATTEMPTS:
        raise ApiError(429, "too_many_attempts", "Too many wrong codes. Ask for a new one.")
    if row.get("email_otp_code"):
        match = hmac.compare_digest(row["email_otp_code"], body.code)
    else:   # legacy hashed codes, from before readable storage
        match = hmac.compare_digest(row["email_otp_hash"], sha256_hex(f"{session_id}:{body.code}"))
    if not match:
        await db.run("update onboarding_sessions set email_otp_attempts = email_otp_attempts + 1 where id = :id",
                     {"id": session_id})
        raise bad_request("That code isn't right. Check the latest e-mail and try again.", "code_wrong")
    await db.run(
        """update onboarding_sessions
              set email_verified_at = :now, email_verified_for = company_email,
                  email_otp_code = null, email_otp_hash = null,
                  status = 'email_verified'
            where id = :id""", {"now": now, "id": session_id})
    return {"verified": True}


class CompleteIn(BaseModel):
    authorized: bool = False


@router.post("/sessions/{session_id}/complete", status_code=201)
async def complete_onboarding(session_id: UUID, body: CompleteIn, request: Request,
                              db: TenantDb = Depends(onboarding_db)):
    """Create the company. Every gate must already be green: parsed/valid W-9 or
    manual+CIN+MOA, unique tax ID, verified e-mail, and the authorization checkbox.
    The creator becomes the company's Super Admin."""
    row = await _session(db, session_id)
    if not body.authorized:
        raise bad_request("Tick the authorization box to confirm you may register this business")
    payload = row["payload"] or {}
    details = payload.get("details", {})
    if not details.get("kind") or not details.get("domain"):
        raise ApiError(422, "incomplete", "Save the company details first")
    email = row.get("company_email")
    if not email or not row.get("email_verified_at") or row.get("email_verified_for") != email:
        raise ApiError(422, "email_unverified", "Verify the company e-mail with the OTP code first")

    tax: dict = {}
    if row["country"] == "US":
        w9 = payload.get("w9") or {}
        legal = (w9.get("legal_name") or "").strip()
        digits = _digits(w9.get("ein") or w9.get("tin"))
        if not legal or len(digits) != 9:
            raise ApiError(422, "incomplete", "The W-9 details are incomplete — re-upload or correct them")
        taken = await _ein_taken(db, digits)
        if taken:
            raise conflict(f"This EIN is already registered to {taken['name']} ({taken['business_code']})")
        ein = (f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
               if (w9.get("tin_type") or "").lower() == "ssn" else f"{digits[:2]}-{digits[2:]}")
        w9_data = {k: w9.get(k) for k in
                   ("legal_name", "dba", "tax_classification", "tin", "tin_type",
                    "address", "city", "state", "zip")}
        w9_data["tin"] = ein
        tax = {"tin": ein, "ein": None if (w9.get("tin_type") or "").lower() == "ssn" else ein, "tax_classification": w9.get("tax_classification"),
               "tax_address": ", ".join(p for p in
                                        [w9.get("address"), w9.get("city"),
                                         f"{w9.get('state') or ''} {w9.get('zip') or ''}".strip()] if p),
               "w9_data": orjson.dumps(w9_data).decode(),
               "w9_status": "submitted", "w9_document_id": w9.get("document_id")}
    else:
        for key in ("legal_name", "cin", "street", "city", "state", "pin"):
            if not (details.get(key) or "").strip():
                raise ApiError(422, "incomplete", "Complete the manual details first")
        cin = _norm_cin(details.get("cin"))
        if not CIN_RE.match(cin):
            raise ApiError(422, "invalid_cin", "CIN must look like L12345MH2020PLC123456 (21 characters)")
        dup = await db.val("select business_code from companies where tenant_id = :t and cin = :c",
                           {"t": db.ctx.tenant_id, "c": cin})
        if dup:
            raise conflict(f"This CIN is already registered to business {dup}")
        if not (payload.get("moa") or {}).get("document_id"):
            raise ApiError(422, "moa_required", "Upload the Memorandum of Association (MOA) first")
        tax = {"cin": cin}

    code = await _assign_business_code(db)
    # Same default as a direct create: the wizard doesn't ask — a new business
    # can play any role, so it starts with all four. Narrow later if needed.
    detail_kinds = details.get("kinds") if details.get("kinds") is not None else list(COMPANY_KINDS)
    primary, roles = _roles(details.get("kind"), detail_kinds)
    if row["country"] == "US":
        w9 = payload.get("w9") or {}
        name = (w9.get("legal_name") or "").strip()
        state = (w9.get("state") or "").strip()[:2].upper() or None
        cols = {"name": name, "state": state, "btype": w9.get("business_type"),
                "dba": details.get("dba") or w9.get("dba"),
                "cin": None, "ein": tax["ein"], "tin": tax["tin"], "tclass": tax["tax_classification"],
                "taddr": tax["tax_address"], "w9": tax["w9_data"], "w9s": "submitted", "w9doc": tax["w9_document_id"]}
    else:
        name = (details.get("legal_name") or "").strip()
        state = (details.get("state") or "").strip() or None
        cols = {"name": name, "state": state, "btype": None, "dba": details.get("dba"),
                "cin": tax["cin"], "ein": None, "tin": None, "tclass": None,
                "taddr": f"{details.get('street')}, {details.get('city')}, {state} {details.get('pin')}".strip(),
                "w9": "{}", "w9s": "draft", "w9doc": None}
    if row["country"] == "US":
        address = tax["tax_address"]
    else:
        address = (", ".join(p for p in [details.get("street"), details.get("city"),
                                         f"{details.get('state') or ''} {details.get('pin') or ''}".strip()]
                             if p) or None)
    try:
        async with db.conn.begin_nested():
            company = await db.one(
                """insert into companies (tenant_id, business_code, name, kind, kinds, country, cin, ein, state, address,
                                          contact_name, contact_email, contact_phone, default_terms, domain,
                                          business_type, dba, tin, tax_classification, tax_address, w9_data, w9_status,
                                          w9_document_id, status, onboarding_stage, created_by)
                   values (:t, :code, :name, :kind, cast(:kinds as text[]), :country, :cin, :ein, :state, :address, :cn, :ce, :cp, 'Net 30',
                           :domain, :btype, :dba, :tin, :tclass, :taddr, cast(:w9 as jsonb), :w9s, :w9doc,
                           'onboarding', 1, :u)
                   returning id, business_code, status""",
                {"t": db.ctx.tenant_id, "code": code, "kind": primary, "kinds": roles, "country": row["country"],
                 "cn": details.get("contact_name"), "ce": email, "cp": details.get("contact_phone"),
                 "domain": details.get("domain"), **cols, "address": address, "u": db.ctx.user_id})
    except IntegrityError as exc:
        raise conflict("A company with these details already exists") from exc

    doc_ids = [UUID(d) for d in (tax.get("w9_document_id"), (payload.get("moa") or {}).get("document_id")) if d]
    if doc_ids:
        await db.run("update documents set owner_type = 'company', owner_id = :c where id = any(cast(:ids as uuid[]))",
                     {"c": company["id"], "ids": doc_ids})
    if row["country"] == "US":
        if tax.get("w9_document_id"):
            await db.run(
                """insert into tracked_documents (tenant_id, company_id, doc_type, label, status)
                   values (:t, :c, 'w9', 'Form W-9', 'valid') on conflict do nothing""",
                {"t": db.ctx.tenant_id, "c": company["id"]})
    else:
        await db.run(
            """insert into tracked_documents (tenant_id, company_id, doc_type, label, status)
               values (:t, :c, 'moa', 'Memorandum of Association', 'valid') on conflict do nothing""",
            {"t": db.ctx.tenant_id, "c": company["id"]})
    await db.run(
        """update onboarding_sessions
              set status = 'complete', company_id = :c, authorized_at = :now, auth_ip = :ip
            where id = :id""",
        {"c": company["id"], "now": datetime.now(UTC), "ip": client_ip(request), "id": session_id})
    # Registering my own company (an account still waiting for its profile): link it and name the account.
    await db.run(
        """update tenants set company_id = :c, name = :n, ein = :ein, state = :s
            where id = :t and company_id is null and status = 'onboarding'""",
        {"c": company["id"], "n": cols["name"], "ein": cols["ein"], "s": cols["state"], "t": db.ctx.tenant_id})
    return {"id": company["id"], "company_id": company["id"], "tenant_id": db.ctx.tenant_id,
            "business_code": company["business_code"], "status": company["status"],
            "company_role": "super_admin"}
