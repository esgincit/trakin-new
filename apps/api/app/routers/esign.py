"""E-signatures, sender side: prepare an envelope, send it, remind, void, download.

The signer side (signing link, one-time code, consent, sign/decline with IP address
capture) is in `public.py`.
"""

from __future__ import annotations

from uuid import UUID

import orjson
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, EmailStr, Field, ValidationError

from ..deps import TenantDb, tenant_db
from ..errors import bad_request, conflict, not_found
from ..services import numbering, storage
from ..services.esign import link_expiry, log_event, send_to_signer
from ..utils import sha256_hex

router = APIRouter(prefix="/envelopes", tags=["e-signatures"])

MAX_PDF_BYTES = storage.MAX_UPLOAD
SENDER_ROLES = ("legal", "account_manager", "finance", "hr")


class SignerIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    company: str | None = None
    company_id: UUID | None = None


_SIGNER_COLUMNS = """s.id, s.position, s.name, s.email, s.company, s.company_id, s.status, s.verified_at, s.consented_at,
                     s.signed_at, s.signature_type, s.signed_ip, s.signed_user_agent, s.signed_location,
                     s.declined_reason, s.last_reminded_at"""


@router.get("")
async def list_envelopes(db: TenantDb = Depends(tenant_db), status: str | None = None):
    return await db.all(
        """select e.id, e.number, e.title, e.status, e.sent_at, e.completed_at, e.expires_at, e.sent_by_name,
                  ag.code as agreement, sw.code as sow, c.full_name as consultant,
                  (select count(*) from envelope_signers s where s.envelope_id = e.id) as signers,
                  (select count(*) from envelope_signers s where s.envelope_id = e.id and s.status = 'signed') as signed,
                  (select s.name from envelope_signers s where s.envelope_id = e.id and s.status in ('sent', 'viewed')
                    order by s.position limit 1) as waiting_on
             from envelopes e
             left join agreements ag on ag.id = e.agreement_id
             left join sows sw on sw.id = e.sow_id
             left join consultants c on c.id = e.consultant_id
            where (cast(:s as text) is null or e.status = :s)
            order by e.created_at desc""",
        {"s": status})


@router.get("/{envelope_id}")
async def get_envelope(envelope_id: UUID, db: TenantDb = Depends(tenant_db)):
    env = await db.one("select * from envelopes where id = :id", {"id": envelope_id})
    if env is None:
        raise not_found("Envelope")
    env["signers"] = await db.all(f"select {_SIGNER_COLUMNS} from envelope_signers s where s.envelope_id = :id order by s.position",
                                  {"id": envelope_id})
    env["events"] = await db.all(
        """select ev.event, ev.at, ev.ip, ev.user_agent, ev.location, ev.detail, s.name as signer
             from signature_events ev left join envelope_signers s on s.id = ev.signer_id
            where ev.envelope_id = :id order by ev.at""", {"id": envelope_id})
    return env


@router.post("", status_code=201)
async def create_envelope(
    db: TenantDb = Depends(tenant_db),
    title: str = Form(min_length=3, max_length=200),
    signers: str = Form(description='JSON list: [{"name": "...", "email": "...", "company": "..."}] in signing order'),
    message: str | None = Form(None),
    agreement_id: UUID | None = Form(None),
    sow_id: UUID | None = Form(None),
    amendment_id: UUID | None = Form(None),
    consultant_id: UUID | None = Form(None),
    sequential: bool = Form(True),
    remind_every_days: int = Form(3, ge=1, le=14),
    file: UploadFile | None = File(None, description="The PDF to sign (up to 4 MB through the API)"),
    document_path: str | None = Form(None, description="Or: the path returned by POST /uploads (purpose=esign)"),
):
    """Prepare an envelope (draft). Nothing is sent until you call /send."""
    db.ctx.require(*SENDER_ROLES)
    try:
        people = [SignerIn.model_validate(p) for p in orjson.loads(signers)]
    except (orjson.JSONDecodeError, ValidationError, TypeError) as exc:
        raise bad_request("Signers must be a list of {name, email}") from exc
    if not people:
        raise bad_request("Add at least one signer")
    if len({p.email.lower() for p in people}) != len(people):
        raise bad_request("Each signer needs a different e-mail address")

    if file is not None:
        data = await file.read()
    elif document_path and document_path.startswith(f"{db.ctx.tenant_id}/uploads/") and ".." not in document_path:
        data = await storage.download("esign", document_path)
    else:
        raise bad_request("Attach the PDF to sign")
    if len(data) > MAX_PDF_BYTES:
        raise bad_request("The PDF is larger than 25 MB")
    if not data.startswith(b"%PDF"):
        raise bad_request("Upload a PDF file")

    number = await numbering.next_code(db, "envelope")
    sender = await db.val("select full_name from profiles where id = :u", {"u": db.ctx.user_id})
    env = await db.one(
        """insert into envelopes (tenant_id, number, title, agreement_id, sow_id, amendment_id, consultant_id, document_sha256,
                                  message, sequential, remind_every_days, sent_by, sent_by_name)
           values (:t, :n, :title, :ag, :sow, :amd, :con, :sha, :msg, :seq, :rem, :u, :sender) returning *""",
        {"t": db.ctx.tenant_id, "n": number, "title": title, "ag": agreement_id, "sow": sow_id, "amd": amendment_id,
         "con": consultant_id, "sha": sha256_hex(data), "msg": message, "seq": sequential, "rem": remind_every_days,
         "u": db.ctx.user_id, "sender": sender or db.ctx.email})
    path = f"{db.ctx.tenant_id}/{env['id']}/original.pdf"
    await storage.upload("esign", path, data, "application/pdf", upsert=True)
    await db.run("update envelopes set document_path = :p where id = :id", {"p": path, "id": env["id"]})
    await db.run(
        """insert into envelope_signers (tenant_id, envelope_id, position, name, email, company, company_id)
           values (:t, :e, :pos, :name, :email, :company, :co)""",
        [{"t": db.ctx.tenant_id, "e": env["id"], "pos": i + 1, "name": p.name, "email": p.email, "company": p.company,
          "co": p.company_id} for i, p in enumerate(people)])
    await log_event(db, tenant_id=db.ctx.tenant_id, envelope_id=env["id"], signer_id=None, event="created",
                    ip=db.ctx.ip, user_agent=db.ctx.user_agent, detail={"by": sender or db.ctx.email})
    return await get_envelope(env["id"], db)


@router.post("/{envelope_id}/send")
async def send_envelope(envelope_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Send to the first signer (sequential) or to everyone (parallel)."""
    db.ctx.require(*SENDER_ROLES)
    env = await db.one("select * from envelopes where id = :id for update", {"id": envelope_id})
    if env is None:
        raise not_found("Envelope")
    if env["status"] != "draft":
        raise conflict("This envelope has already been sent")
    env = await db.one("update envelopes set status = 'sent', sent_at = now(), expires_at = :exp where id = :id returning *",
                       {"id": envelope_id, "exp": link_expiry()})
    signers = await db.all("select * from envelope_signers where envelope_id = :id order by position", {"id": envelope_id})
    for signer in signers[:1] if env["sequential"] else signers:
        await send_to_signer(db, envelope=env, signer=signer, sender_name=env["sent_by_name"] or "myTrakIn")
    await _mark_parent(db, env, "out_for_signature")
    return await get_envelope(envelope_id, db)


@router.post("/{envelope_id}/remind")
async def remind(envelope_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Send a fresh link to whoever the envelope is waiting on."""
    db.ctx.require(*SENDER_ROLES)
    env = await db.one("select * from envelopes where id = :id", {"id": envelope_id})
    if env is None:
        raise not_found("Envelope")
    if env["status"] != "sent":
        raise conflict("Only envelopes that are out for signature can be reminded")
    waiting = await db.all("select * from envelope_signers where envelope_id = :id and status in ('sent', 'viewed') order by position",
                           {"id": envelope_id})
    for signer in waiting:
        await send_to_signer(db, envelope=env, signer=signer, sender_name=env["sent_by_name"] or "myTrakIn", is_reminder=True)
    return {"reminded": [s["email"] for s in waiting]}


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/{envelope_id}/void")
async def void(envelope_id: UUID, body: VoidIn, db: TenantDb = Depends(tenant_db)):
    db.ctx.require(*SENDER_ROLES)
    env = await db.one("update envelopes set status = 'voided' where id = :id and status in ('draft', 'sent') returning *",
                       {"id": envelope_id})
    if env is None:
        raise conflict("Only draft or sent envelopes can be voided")
    await db.run("update envelope_signers set token_hash = null where envelope_id = :id", {"id": envelope_id})
    await log_event(db, tenant_id=db.ctx.tenant_id, envelope_id=envelope_id, signer_id=None, event="voided",
                    ip=db.ctx.ip, user_agent=db.ctx.user_agent, detail={"reason": body.reason})
    await _mark_parent(db, env, "draft")
    return {"id": envelope_id, "status": "voided"}


@router.get("/{envelope_id}/download")
async def download(envelope_id: UUID, db: TenantDb = Depends(tenant_db)):
    """A 5-minute link to the sealed PDF (with certificate) or, before completion, the original."""
    env = await db.one("select signed_path, document_path, status from envelopes where id = :id", {"id": envelope_id})
    if env is None:
        raise not_found("Envelope")
    path = env["signed_path"] or env["document_path"]
    if not path:
        raise not_found("Document")
    return {"url": await storage.signed_url("esign", path), "sealed": bool(env["signed_path"])}


async def _mark_parent(db: TenantDb, env: dict, status: str) -> None:
    """Keep the agreement / SOW / amendment status in step with its envelope."""
    if env.get("agreement_id"):
        await db.run("update agreements set status = :s where id = :id and status in ('draft', 'out_for_signature')",
                      {"s": status, "id": env["agreement_id"]})
    if env.get("sow_id"):
        await db.run("update sows set status = :s where id = :id and status in ('draft', 'out_for_signature')",
                      {"s": status, "id": env["sow_id"]})
    if env.get("amendment_id"):
        await db.run("update sow_amendments set status = :s where id = :id and status in ('draft', 'out_for_signature')",
                      {"s": status, "id": env["amendment_id"]})
