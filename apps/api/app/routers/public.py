"""Pages that work without an account.

    /public/sign/{token}        e-signature: view, one-time code, consent, sign or decline
    /public/workspaces/{id}     the registration page of one tenant (vendors, clients, contractors)
    /public/signups             staffing companies asking for their own myTrakIn workspace

Every signing step records the signer's IP address, device and approximate location.
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import orjson
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field

from ..config import get_settings
from ..deps import TenantDb, open_public, open_signer
from ..errors import ApiError, bad_request, conflict, not_found
from ..services import storage
from ..services.email import render, send_email
from ..services.esign import ESIGN_DISCLOSURE, build_certificate, log_event, seal, send_to_signer
from ..utils import approx_location, device_label, otp_code, sha256_hex
from .esign import _mark_parent

log = logging.getLogger("mytrakin.esign")
router = APIRouter(prefix="/public", tags=["public"])

FREE_MAIL = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com", "icloud.com", "proton.me", "protonmail.com"}


# ============================================================================ e-signature
async def signer_db(token: str, request: Request) -> AsyncIterator[TenantDb]:
    if len(token) < 20 or len(token) > 100:
        raise ApiError(404, "link_invalid", "This signing link is not valid. Ask the sender for a new one.")
    async for db in open_signer(request, sha256_hex(token)):
        yield db


async def _load(db: TenantDb) -> tuple[dict, dict, list[dict]]:
    env = await db.one("select * from envelopes where id = :id", {"id": db.ctx.extra["envelope_id"]})
    signers = await db.all("select * from envelope_signers where envelope_id = :id order by position", {"id": env["id"]})
    me = next(s for s in signers if s["id"] == db.ctx.signer_id)
    if env["status"] == "sent" and env["expires_at"] and env["expires_at"] < datetime.now(UTC):
        await db.run("update envelopes set status = 'expired' where id = :id", {"id": env["id"]})
        await _event(db, env, me, "expired")
        env["status"] = "expired"
    return env, me, signers


def _my_turn(env: dict, me: dict, signers: list[dict]) -> bool:
    if not env["sequential"]:
        return True
    return all(s["status"] == "signed" for s in signers if s["position"] < me["position"])


def _require_open(env: dict, me: dict, signers: list[dict]) -> None:
    if env["status"] != "sent":
        raise conflict(f"This envelope is {env['status']} and can't be signed")
    if me["status"] in ("signed", "declined"):
        raise conflict(f"You have already {me['status']} this document")
    if not _my_turn(env, me, signers):
        raise conflict("It isn't your turn yet — you'll get an e-mail when the earlier signers are done")


async def _event(db: TenantDb, env: dict, me: dict | None, event: str, request: Request | None = None,
                 detail: dict | None = None) -> None:
    await log_event(db, tenant_id=env["tenant_id"], envelope_id=env["id"], signer_id=me["id"] if me else None, event=event,
                    ip=db.ctx.ip, user_agent=db.ctx.user_agent,
                    location=approx_location(request) if request else None, detail=detail)


@router.get("/sign/{token}")
async def view(request: Request, db: TenantDb = Depends(signer_db)):
    env, me, signers = await _load(db)
    if me["status"] == "sent" and env["status"] == "sent":
        await db.run("update envelope_signers set status = 'viewed' where id = :id", {"id": me["id"]})
        await _event(db, env, me, "viewed", request)
        me["status"] = "viewed"
    return {
        "envelope": {"number": env["number"], "title": env["title"], "message": env["message"], "status": env["status"],
                     "sent_by": env["sent_by_name"], "sent_at": env["sent_at"], "expires_at": env["expires_at"]},
        "signer": {"name": me["name"], "email": me["email"], "company": me["company"], "status": me["status"],
                   "verified": me["verified_at"] is not None, "consented": me["consented_at"] is not None},
        "signers": [{"position": s["position"], "name": s["name"], "company": s["company"], "status": s["status"]}
                    for s in signers],
        "my_turn": _my_turn(env, me, signers),
        "disclosure": ESIGN_DISCLOSURE,
        "your_ip": db.ctx.ip,
    }


@router.post("/sign/{token}/code")
async def send_code(request: Request, db: TenantDb = Depends(signer_db)):
    """E-mail a 6-digit code to the signer's address (proves they control it)."""
    env, me, signers = await _load(db)
    _require_open(env, me, signers)
    settings = get_settings()
    now = datetime.now(UTC)
    if me["otp_expires_at"] and me["otp_expires_at"] - timedelta(minutes=settings.otp_ttl_minutes) > now - timedelta(seconds=45):
        raise ApiError(429, "too_soon", "A code was just sent. Please wait a minute before asking for another.")
    code = otp_code()
    await db.run("update envelope_signers set otp_hash = :h, otp_expires_at = :exp, otp_attempts = 0 where id = :id",
                 {"h": sha256_hex(f"{me['id']}:{code}"), "exp": now + timedelta(minutes=settings.otp_ttl_minutes), "id": me["id"]})
    await send_email(db, to=me["email"], subject=f"Your signing code: {code}", kind="esign_code", tenant_id=env["tenant_id"],
                     ref_type="envelope", ref_id=env["id"],
                     html_body=render("Your one-time signing code",
                                      [f"Enter {code} to open “{env['title']}”.",
                                       f"The code expires in {settings.otp_ttl_minutes} minutes. If you didn't ask for it, ignore this e-mail."]))
    return {"sent_to": _mask(me["email"])}


class CodeIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


@router.post("/sign/{token}/verify")
async def verify(body: CodeIn, request: Request, db: TenantDb = Depends(signer_db)):
    env, me, signers = await _load(db)
    _require_open(env, me, signers)
    settings = get_settings()
    if not me["otp_hash"] or not me["otp_expires_at"] or me["otp_expires_at"] < datetime.now(UTC):
        raise bad_request("The code has expired. Ask for a new one.", "code_expired")
    if me["otp_attempts"] >= settings.otp_max_attempts:
        raise ApiError(429, "too_many_attempts", "Too many wrong codes. Ask for a new one.")
    if not hmac.compare_digest(me["otp_hash"], sha256_hex(f"{me['id']}:{body.code}")):
        await db.run("update envelope_signers set otp_attempts = otp_attempts + 1 where id = :id", {"id": me["id"]})
        raise bad_request("That code isn't right. Check the latest e-mail and try again.", "code_wrong")
    await db.run("update envelope_signers set verified_at = now(), otp_hash = null where id = :id", {"id": me["id"]})
    await _event(db, env, me, "verified", request, {"method": "email_otp"})
    return {"verified": True}


@router.post("/sign/{token}/consent")
async def consent(request: Request, db: TenantDb = Depends(signer_db)):
    """The signer agrees to do business electronically (ESIGN Act § 101(c))."""
    env, me, signers = await _load(db)
    _require_open(env, me, signers)
    if me["verified_at"] is None:
        raise bad_request("Verify your e-mail first", "not_verified")
    await db.run("update envelope_signers set consented_at = now() where id = :id", {"id": me["id"]})
    await _event(db, env, me, "consented", request, {"disclosure_sha256": sha256_hex(ESIGN_DISCLOSURE)})
    return {"consented": True}


@router.get("/sign/{token}/document")
async def document(db: TenantDb = Depends(signer_db)):
    """The PDF to review. Opens only after the e-mail code is verified."""
    env, me, _ = await _load(db)
    if me["verified_at"] is None:
        raise bad_request("Verify your e-mail first", "not_verified")
    path = env["signed_path"] if env["status"] == "completed" and env["signed_path"] else env["document_path"]
    if storage.is_remote():
        # A short-lived link straight to storage: large PDFs can't pass through a Vercel Function.
        return {"url": await storage.signed_url("esign", path, expires_in=600)}
    data = await storage.download("esign", path)
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{env["number"]}.pdf"', "Cache-Control": "no-store"})


class SignIn(BaseModel):
    signature_type: str = Field(pattern="^(typed|drawn)$")
    signature_data: str = Field(min_length=2, max_length=400_000)
    agree: bool


@router.post("/sign/{token}/sign")
async def sign(body: SignIn, request: Request, db: TenantDb = Depends(signer_db)):
    env, me, signers = await _load(db)
    _require_open(env, me, signers)
    if me["verified_at"] is None or me["consented_at"] is None:
        raise bad_request("Verify your e-mail and accept electronic signing first", "not_ready")
    if not body.agree:
        raise bad_request("Tick the box to confirm you intend to sign")
    if body.signature_type == "drawn" and not body.signature_data.startswith("data:image/png;base64,"):
        raise bad_request("A drawn signature must be a PNG image")
    if body.signature_type == "typed" and len(body.signature_data) > 120:
        raise bad_request("A typed signature can be at most 120 characters")

    location = approx_location(request)
    await db.run(
        """update envelope_signers set status = 'signed', signed_at = now(), signature_type = :t, signature_data = :d,
                  signed_ip = :ip, signed_user_agent = :ua, signed_location = :loc, token_hash = null
            where id = :id""",
        {"t": body.signature_type, "d": body.signature_data, "ip": db.ctx.ip, "ua": device_label(db.ctx.user_agent),
         "loc": location, "id": me["id"]})
    await _event(db, env, me, "signed", request, {"type": body.signature_type, "document_sha256": env["document_sha256"]})

    signers = await db.all("select * from envelope_signers where envelope_id = :id order by position", {"id": env["id"]})
    if all(s["status"] == "signed" for s in signers):
        await _complete(db, env)
        return {"status": "completed", "message": "Thank you — everyone has signed. A copy is on its way to your inbox."}
    if env["sequential"]:
        nxt = next(s for s in signers if s["status"] != "signed")
        if nxt["status"] == "waiting":
            await send_to_signer(db, envelope=env, signer=nxt, sender_name=env["sent_by_name"] or "myTrakIn")
    return {"status": "signed", "message": "Thank you — your signature is recorded. We'll e-mail the completed copy."}


class DeclineIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/sign/{token}/decline")
async def decline(body: DeclineIn, request: Request, db: TenantDb = Depends(signer_db)):
    env, me, signers = await _load(db)
    _require_open(env, me, signers)
    await db.run("update envelope_signers set status = 'declined', declined_reason = :r, token_hash = null where id = :id",
                 {"r": body.reason, "id": me["id"]})
    await db.run("update envelopes set status = 'declined' where id = :id", {"id": env["id"]})
    await _event(db, env, me, "declined", request, {"reason": body.reason})
    await _as_system(db, env["tenant_id"])   # signers can't read staff profiles
    sender = await db.val("select email from profiles where id = :u", {"u": env["sent_by"]}) if env["sent_by"] else None
    if sender:
        await send_email(db, to=sender, subject=f"Declined: {env['title']}", kind="esign", tenant_id=env["tenant_id"],
                         ref_type="envelope", ref_id=env["id"],
                         html_body=render(f"{me['name']} declined to sign", [env["title"], f"Reason: {body.reason}"]))
    return {"status": "declined"}


async def _complete(db: TenantDb, env: dict) -> None:
    """Everyone signed: seal the PDF with the certificate, file it, and tell everyone.

    The signer's context can't update agreements or SOWs, so the finishing steps run as
    the tenant's system context inside the same transaction.
    """
    await _as_system(db, env["tenant_id"])
    env = await db.one("update envelopes set status = 'completed', completed_at = now() where id = :id returning *", {"id": env["id"]})
    signers = await db.all("select * from envelope_signers where envelope_id = :id order by position", {"id": env["id"]})
    await log_event(db, tenant_id=env["tenant_id"], envelope_id=env["id"], signer_id=None, event="completed")
    events = await db.all("select * from signature_events where envelope_id = :id order by at", {"id": env["id"]})

    original = await storage.download("esign", env["document_path"]) if env["document_path"] else None
    sealed = seal(original, build_certificate(env, signers, events, env["document_sha256"]))
    path = f"{env['tenant_id']}/{env['id']}/signed.pdf"
    await storage.upload("esign", path, sealed, "application/pdf", upsert=True)
    await db.run("update envelopes set signed_path = :p, signed_sha256 = :h where id = :id",
                 {"p": path, "h": sha256_hex(sealed), "id": env["id"]})

    # Contract records follow their envelope.
    names = ", ".join(s["name"] for s in signers)
    if env["agreement_id"]:
        await db.run("update agreements set status = 'active', signed_by = :n, signed_file_path = :p where id = :id",
                     {"n": names, "p": path, "id": env["agreement_id"]})
    if env["sow_id"]:
        await db.run("update sows set status = 'active', signed_file_path = :p where id = :id", {"p": path, "id": env["sow_id"]})
    if env["amendment_id"]:
        await _mark_parent(db, {"amendment_id": env["amendment_id"]}, "signed")
        await db.run(
            """update sows s set end_date = coalesce(a.new_end_date, s.end_date),
                      value_cap = case when a.value_change is null then s.value_cap else coalesce(s.value_cap, 0) + a.value_change end
                 from sow_amendments a where a.id = :id and s.id = a.sow_id""", {"id": env["amendment_id"]})
    # WF-06: the signature is the acceptance — keep it in the acceptance history.
    for entity_type, entity_id in (("agreement", env["agreement_id"]), ("sow", env["sow_id"]),
                                   ("amendment", env["amendment_id"])):
        if entity_id:
            await db.run(
                """insert into acceptances (tenant_id, entity_type, entity_id, accepted_by, method, envelope_id)
                   values (:t, :type, :id, :by, 'esign', :env)""",
                {"t": env["tenant_id"], "type": entity_type, "id": entity_id, "by": names, "env": env["id"]})

    link = await storage.signed_url("esign", path, expires_in=7 * 24 * 3600)
    sender = await db.val("select email from profiles where id = :u", {"u": env["sent_by"]}) if env["sent_by"] else None
    # The sender is often a signer too: one copy per address.
    recipients = list({e.lower(): e for e in [*(s["email"] for s in signers), *([sender] if sender else [])]}.values())
    await send_email(db, to=recipients, subject=f"Completed: {env['title']}", kind="esign", tenant_id=env["tenant_id"],
                     ref_type="envelope", ref_id=env["id"],
                     html_body=render("Everyone has signed", [env["title"], f"Signed by {names}.",
                                                              "The download link works for 7 days. The PDF includes the certificate "
                                                              "of completion with each signer's time, IP address and device."],
                                      button=("Download signed PDF", link)))


async def _as_system(db: TenantDb, tenant_id) -> None:
    await db.run("select mytrakin.begin_request(null, :t, 'system', null, null, :ip, :ua)",
                 {"t": tenant_id, "ip": db.ctx.ip, "ua": db.ctx.user_agent})


def _mask(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:2]}{'•' * max(1, len(name) - 2)}@{domain}"


# ============================================================================ registration
async def workspace_db(tenant_id: UUID, request: Request) -> AsyncIterator[TenantDb]:
    async for db in open_public(request, tenant_id):
        yield db


@router.get("/workspaces/{tenant_id}")
async def workspace(db: TenantDb = Depends(workspace_db)):
    """Name of the company whose registration page this is."""
    tenant = await db.one("select name from tenants where id = :t and status in ('onboarding', 'active')", {"t": db.ctx.tenant_id})
    if tenant is None:
        raise not_found("Registration page")
    return {"name": tenant["name"], "kinds": ["client", "vendor", "1099", "consultant"]}


@router.post("/workspaces/{tenant_id}/registrations", status_code=201)
async def register(
    db: TenantDb = Depends(workspace_db),
    kind: str = Form(pattern="^(client|vendor|1099|consultant)$"),
    name: str = Form(min_length=2, max_length=200),
    contact: str = Form(min_length=2, max_length=120),
    email: EmailStr = Form(),
    phone: str | None = Form(None),
    state: str | None = Form(None, max_length=2),
    ein: str | None = Form(None, pattern=r"^\d{2}-?\d{7}$"),
    files: list[UploadFile] | None = File(None, description="W-9, certificate of incorporation, COI ..."),
):
    """A vendor, client or contractor registers. Staff review and approve it in Compliance."""
    await workspace(db)
    files = files or []
    if len(files) > 6:
        raise bad_request("Attach at most 6 files")
    domain = email.split("@")[1].lower()
    checks = {"email_free_domain": domain in FREE_MAIL, "ein_given": bool(ein), "submitted_ip": db.ctx.ip}
    # Visitors may insert but not read registrations back, so the id is made here (no RETURNING).
    reg = {"id": uuid4()}
    await db.run(
        """insert into registrations (id, tenant_id, kind, name, contact, email, phone, state, ein, checks, documents)
           values (:id, :t, :k, :n, :c, :e, :p, :s, :ein, cast(:checks as jsonb), cast(:docs as jsonb))""",
        {"id": reg["id"], "t": db.ctx.tenant_id, "k": kind, "n": name.strip(), "c": contact.strip(), "e": email, "p": phone,
         "s": state.upper() if state else None, "ein": ein, "checks": orjson.dumps(checks).decode(),
         "docs": orjson.dumps([f.filename for f in files]).decode()})
    for f in files:
        data = await f.read()
        if len(data) > storage.DIRECT_LIMIT:
            raise bad_request(f"{f.filename} is larger than 4 MB — please send a smaller scan")
        path = f"{db.ctx.tenant_id}/registrations/{reg['id']}/{_safe_name(f.filename)}"
        await storage.upload("documents", path, data, f.content_type or "application/octet-stream")
        await db.run(
            """insert into documents (tenant_id, owner_type, owner_id, name, storage_path, mime_type, size_bytes, sha256)
               values (:t, 'registration', :o, :n, :p, :m, :s, :h)""",
            {"t": db.ctx.tenant_id, "o": reg["id"], "n": f.filename, "p": path, "m": f.content_type, "s": len(data),
             "h": sha256_hex(data)})
    await send_email(db, to=email, subject="We received your registration", kind="registration", tenant_id=db.ctx.tenant_id,
                     ref_type="registration", ref_id=reg["id"],
                     html_body=render("Thanks for registering", [f"We received the registration for {name}.",
                                                                 "Our team reviews new registrations within two business days. "
                                                                 "We'll e-mail you when it is approved or if we need anything else."]))
    return {"id": reg["id"], "status": "pending"}


def _safe_name(filename: str | None) -> str:
    keep = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in (filename or "file"))
    return keep[-120:] or "file"
