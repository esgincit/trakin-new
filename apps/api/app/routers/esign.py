"""E-signatures, sender side: prepare an envelope, send it, remind, void, download.

The signer side (signing link, one-time code, consent, sign/decline with IP address
capture) is in `public.py`.
"""

from __future__ import annotations

import re
from uuid import UUID

import orjson
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, EmailStr, Field, ValidationError

from ..config import get_settings
from ..deps import TenantDb, tenant_db
from ..errors import bad_request, conflict, not_found
from ..services import numbering, storage
from ..services.email import render, send_email
from ..services.esign import combined_document, link_expiry, log_event, send_to_signer
from ..utils import sha256_hex

router = APIRouter(prefix="/envelopes", tags=["e-signatures"])

MAX_PDF_BYTES = storage.MAX_UPLOAD
MAX_DOCUMENTS = 10
MAX_TOTAL_BYTES = 100 * 1024 * 1024      # the packet is merged in one piece, so cap the whole
SENDER_ROLES = ("legal", "account_manager", "finance", "hr")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class SignerIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    company: str | None = None
    company_id: UUID | None = None


_SIGNER_COLUMNS = """s.id, s.position, s.name, s.email, s.company, s.company_id, s.status, s.verified_at, s.consented_at,
                     s.signed_at, s.signature_type, s.signed_ip, s.signed_user_agent, s.signed_location,
                     s.declined_reason, s.last_reminded_at"""


# --------------------------------------------------------------------------- who signs
async def _own_company(db: TenantDb) -> UUID | None:
    """The company this workspace acts as (its membership link, else the workspace's own)."""
    return await db.val(
        """select coalesce(
                    (select company_id from memberships where id = cast(:m as uuid)),
                    (select company_id from tenants where id = :t))""",
        {"m": db.ctx.membership_id, "t": db.ctx.tenant_id})


async def _counterparty_company(db: TenantDb, *, agreement_id: UUID | None, sow_id: UUID | None,
                                amendment_id: UUID | None) -> UUID | None:
    """The company on the other side of what we are sending: the agreement's counterparty,
    resolved through a SOW or an amendment. Ourselves are never the counterparty."""
    agreement = None
    if agreement_id:
        agreement = await db.val("select company_id from agreements where id = :id", {"id": agreement_id})
    elif sow_id or amendment_id:
        agreement = await db.val(
            """select a.company_id from sow_amendments m
                 join sows s on s.id = m.sow_id join agreements a on a.id = s.agreement_id
                where m.id = :amd""",
            {"amd": amendment_id}) if amendment_id else await db.val(
            "select a.company_id from sows s join agreements a on a.id = s.agreement_id where s.id = :sow",
            {"sow": sow_id})
    if not agreement:
        return None
    if agreement == await _own_company(db):
        return await db.val("select initiator_company_id from agreements where id = :id", {"id": agreement_id})
    return agreement


async def _admins_of(db: TenantDb, company_id: UUID | None) -> list[dict]:
    """Who may sign for a company (owners and admins), strongest role first."""
    if not company_id:
        return []
    rows = await db.all("select * from mytrakin.company_signing_admins(:c)", {"c": company_id})
    name = await db.val("select mytrakin.company_public_name(:c)", {"c": company_id})
    return [{**r, "company": name, "company_id": company_id} for r in rows]


@router.get("/signing-parties")
async def signing_parties(
    db: TenantDb = Depends(tenant_db),
    agreement_id: UUID | None = None,
    sow_id: UUID | None = None,
    amendment_id: UUID | None = None,
):
    """Who is expected to sign: us (the person sending, from their own company) and the
    people who may sign for the other company. The counterparty's admins are offered as a
    pick list rather than typed in — a document can only ask the company's own admins to
    sign for it. Their company record itself stays unreadable (RULE-01)."""
    db.ctx.require(*SENDER_ROLES)
    me = await db.one("select full_name, email from profiles where id = :u", {"u": db.ctx.user_id})
    own_id = await _own_company(db)
    counterparty_id = await _counterparty_company(
        db, agreement_id=agreement_id, sow_id=sow_id, amendment_id=amendment_id)
    return {
        "creator": {
            "name": (me or {}).get("full_name") or db.ctx.email,
            "email": (me or {}).get("email") or db.ctx.email,
            "company": await db.val("select mytrakin.company_public_name(:c)", {"c": own_id}),
            "company_id": own_id,
        },
        "counterparty": {
            "id": counterparty_id,
            "name": await db.val("select mytrakin.company_public_name(:c)", {"c": counterparty_id}),
        } if counterparty_id else None,
        "signers": await _admins_of(db, counterparty_id),
    }


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
    env["documents"] = await db.all(
        "select id, position, name, sha256, size_bytes, created_at from envelope_documents "
        "where envelope_id = :id order by position", {"id": envelope_id})
    env["events"] = await db.all(
        """select ev.event, ev.at, ev.ip, ev.user_agent, ev.location, ev.detail, s.name as signer
             from signature_events ev left join envelope_signers s on s.id = ev.signer_id
            where ev.envelope_id = :id order by ev.at""", {"id": envelope_id})
    return env


# --------------------------------------------------------------------------- documents
async def _read_document(db: TenantDb, upload: UploadFile) -> tuple[str, bytes]:
    """(name, bytes) for one uploaded PDF, with the same checks as a single file."""
    name = upload.filename or "document.pdf"
    if (upload.content_type or "") not in {"application/pdf", ""}:
        raise bad_request(f"{name} isn't a PDF — attach PDF files only")
    data = await upload.read()
    if not data:
        raise bad_request(f"{name} is empty")
    if len(data) > MAX_PDF_BYTES:
        raise bad_request(f"{name} is larger than 25 MB")
    if not data.startswith(b"%PDF"):
        raise bad_request(f"{name} isn't a valid PDF")
    return name, data


async def _read_stored(db: TenantDb, path: str) -> tuple[str, bytes]:
    """(name, bytes) for a file already in storage (uploaded through POST /uploads)."""
    if not path.startswith(f"{db.ctx.tenant_id}/uploads/") or ".." in path:
        raise bad_request("That upload doesn't belong to this workspace")
    return path.rsplit("/", 1)[-1], await storage.download("esign", path)


async def _rebuild_merged(db: TenantDb, envelope_id: UUID) -> None:
    """Re-create "the document that gets signed" from the envelope's files, in order."""
    docs = await db.all(
        "select storage_path from envelope_documents where envelope_id = :id order by position", {"id": envelope_id})
    blobs = [await storage.download("esign", d["storage_path"]) for d in docs]
    combined = combined_document(blobs)
    path = f"{db.ctx.tenant_id}/{envelope_id}/original.pdf"
    await storage.upload("esign", path, combined, "application/pdf", upsert=True)
    await db.run("update envelopes set document_path = :p, document_sha256 = :h where id = :id",
                 {"p": path, "h": sha256_hex(combined), "id": envelope_id})


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
    files: list[UploadFile] | None = File(None, description="The PDFs to sign, in order (up to 10)"),
    document_paths: str | None = Form(None, description='JSON list of paths from POST /uploads (purpose=esign)'),
    file: UploadFile | None = File(None, description="One PDF — the older single-file field"),
    document_path: str | None = Form(None, description="One stored path — the older single-file field"),
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

    incoming: list[tuple[str, bytes]] = []
    for upload in files or []:
        incoming.append(await _read_document(db, upload))
    if document_paths:
        try:
            paths = orjson.loads(document_paths)
        except orjson.JSONDecodeError as exc:
            raise bad_request("document_paths must be a JSON list of upload paths") from exc
        if not isinstance(paths, list):
            raise bad_request("document_paths must be a JSON list of upload paths")
        for p in paths:
            incoming.append(await _read_stored(db, str(p)))
    if file is not None:                                   # older single-document callers
        incoming.append(await _read_document(db, file))
    elif document_path:
        incoming.append(await _read_stored(db, document_path))
    if not incoming:
        raise bad_request("Attach at least one PDF to sign")
    if len(incoming) > MAX_DOCUMENTS:
        raise bad_request(f"An envelope can hold up to {MAX_DOCUMENTS} documents")
    if sum(len(b) for _, b in incoming) > MAX_TOTAL_BYTES:
        raise bad_request("These documents add up to more than 100 MB — send them as separate envelopes")

    number = await numbering.next_code(db, "envelope")
    sender = await db.val("select full_name from profiles where id = :u", {"u": db.ctx.user_id})
    env = await db.one(
        """insert into envelopes (tenant_id, number, title, agreement_id, sow_id, amendment_id, consultant_id, document_sha256,
                                  message, sequential, remind_every_days, sent_by, sent_by_name)
           values (:t, :n, :title, :ag, :sow, :amd, :con, :sha, :msg, :seq, :rem, :u, :sender) returning *""",
        {"t": db.ctx.tenant_id, "n": number, "title": title, "ag": agreement_id, "sow": sow_id, "amd": amendment_id,
         "con": consultant_id, "sha": sha256_hex(combined_document([b for _, b in incoming])), "msg": message,
         "seq": sequential, "rem": remind_every_days, "u": db.ctx.user_id, "sender": sender or db.ctx.email})
    for i, (name, data) in enumerate(incoming):
        safe = _SAFE_NAME.sub("-", name).strip("-") or f"document-{i + 1}.pdf"
        path = f"{db.ctx.tenant_id}/{env['id']}/{i + 1:02d}-{safe}"
        await storage.upload("esign", path, data, "application/pdf", upsert=True)
        await db.run(
            """insert into envelope_documents (tenant_id, envelope_id, position, name, storage_path, sha256, size_bytes)
               values (:t, :e, :pos, :name, :path, :sha, :size)""",
            {"t": db.ctx.tenant_id, "e": env["id"], "pos": i + 1, "name": name, "path": path,
             "sha": sha256_hex(data), "size": len(data)})
    await _rebuild_merged(db, env["id"])
    await db.run(
        """insert into envelope_signers (tenant_id, envelope_id, position, name, email, company, company_id)
           values (:t, :e, :pos, :name, :email, :company, :co)""",
        [{"t": db.ctx.tenant_id, "e": env["id"], "pos": i + 1, "name": p.name, "email": p.email, "company": p.company,
          "co": p.company_id} for i, p in enumerate(people)])
    await log_event(db, tenant_id=db.ctx.tenant_id, envelope_id=env["id"], signer_id=None, event="created",
                    ip=db.ctx.ip, user_agent=db.ctx.user_agent,
                    detail={"by": sender or db.ctx.email, "documents": [n for n, _ in incoming]})
    return await get_envelope(env["id"], db)


@router.get("/{envelope_id}/documents/{document_id}/download")
async def download_document(envelope_id: UUID, document_id: UUID, db: TenantDb = Depends(tenant_db)):
    """A link to one document of the envelope, so it can be read without signing anything."""
    doc = await db.one("select id, name from envelope_documents where id = :d and envelope_id = :e",
                       {"d": document_id, "e": envelope_id})
    if doc is None:
        raise not_found("Document")
    path = await db.val("select storage_path from envelope_documents where id = :d", {"d": document_id})
    return {"id": str(doc["id"]), "name": doc["name"], "url": await storage.signed_url("esign", path)}


@router.post("/{envelope_id}/documents", status_code=201)
async def add_document(envelope_id: UUID, db: TenantDb = Depends(tenant_db),
                       file: UploadFile | None = File(None), document_path: str | None = Form(None)):
    """Add one more PDF to a draft envelope (an exhibit, a SOW under the MSA)."""
    db.ctx.require(*SENDER_ROLES)
    env = await db.one("select status from envelopes where id = :id", {"id": envelope_id})
    if env is None:
        raise not_found("Envelope")
    if env["status"] != "draft":
        raise conflict("Documents can only be added while the envelope is a draft")
    count = await db.val("select count(*) from envelope_documents where envelope_id = :id", {"id": envelope_id})
    if count >= MAX_DOCUMENTS:
        raise bad_request(f"An envelope can hold up to {MAX_DOCUMENTS} documents")
    if file is not None:
        name, data = await _read_document(db, file)
    elif document_path:
        name, data = await _read_stored(db, document_path)
    else:
        raise bad_request("Attach a PDF to add")
    position = int(count) + 1
    safe = _SAFE_NAME.sub("-", name).strip("-") or f"document-{position}.pdf"
    path = f"{db.ctx.tenant_id}/{envelope_id}/{position:02d}-{safe}"
    await storage.upload("esign", path, data, "application/pdf", upsert=True)
    doc = await db.one(
        """insert into envelope_documents (tenant_id, envelope_id, position, name, storage_path, sha256, size_bytes)
           values (:t, :e, :pos, :name, :path, :sha, :size) returning id, position, name, sha256, size_bytes, created_at""",
        {"t": db.ctx.tenant_id, "e": envelope_id, "pos": position, "name": name, "path": path,
         "sha": sha256_hex(data), "size": len(data)})
    await _rebuild_merged(db, envelope_id)
    return doc


@router.delete("/{envelope_id}/documents/{document_id}")
async def remove_document(envelope_id: UUID, document_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Take a document out of a draft envelope and renumber what is left."""
    db.ctx.require(*SENDER_ROLES)
    env = await db.one("select status from envelopes where id = :id", {"id": envelope_id})
    if env is None:
        raise not_found("Envelope")
    if env["status"] != "draft":
        raise conflict("Documents can only be removed while the envelope is a draft")
    remaining = await db.val("select count(*) from envelope_documents where envelope_id = :id", {"id": envelope_id})
    removed = await db.one("delete from envelope_documents where id = :d and envelope_id = :e returning id",
                           {"d": document_id, "e": envelope_id})
    if removed is None:
        raise not_found("Document")
    if remaining <= 1:
        raise conflict("An envelope needs at least one document — add another before removing this one")
    await db.run("""update envelope_documents set position = rn.pos from
                       (select id, row_number() over (order by position, created_at) as pos
                          from envelope_documents where envelope_id = :e) rn
                    where envelope_documents.id = rn.id""", {"e": envelope_id})
    await _rebuild_merged(db, envelope_id)
    return {"removed": str(document_id), "remaining": remaining - 1}


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
    await _notify_counterparty(db, env)
    result = await get_envelope(envelope_id, db)
    result["notified"] = await _last_notified(db, envelope_id)
    return result


async def _last_notified(db: TenantDb, envelope_id: UUID) -> list[str]:
    """Who the notification actually went to (shown on the envelope after sending)."""
    return await db.val(
        """select to_address from notifications
            where ref_type = 'envelope' and ref_id = :id and kind = 'esign_notice'
            order by sent_at desc limit 1""",
        {"id": envelope_id}) or []


async def _notify_counterparty(db: TenantDb, env: dict) -> None:
    """Tell every admin of the other company that a document is waiting on them.

    They are not all signers, but the agreement is theirs to action: the person who
    signs may not be the person who owns it. Signers get the signing link from
    send_envelope; this is the announcement for the rest of the company's admins.
    """
    company_id = await _counterparty_company(
        db, agreement_id=env.get("agreement_id"), sow_id=env.get("sow_id"), amendment_id=env.get("amendment_id"))
    admins = await _admins_of(db, company_id)
    if not admins:
        return
    to = [a["email"] for a in admins]
    count = await db.val("select count(*) from envelope_documents where envelope_id = :e", {"e": env["id"]})
    sender_name = env.get("sent_by_name") or "myTrakIn"
    paragraphs = [
        f"{sender_name} has sent a document for electronic signature.",
        env.get("message") or "",
        f"{count or 1} document{'s' if (count or 1) > 1 else ''} attached. "
        f"The signer{'s have' if (count or 1) > 1 else ' has'} been e-mailed a personal link.",
        "You are receiving this because you administer a company this agreement is with.",
    ]
    await send_email(db, to=to, subject=f"For signature: {env['title']}",
                     html_body=render(env["title"], [p for p in paragraphs if p],
                                      button=("Open myTrakIn", workspace_link()),
                                      footer=f"Regarding {admins[0].get('company') or 'your company'}."),
                     kind="esign_notice", tenant_id=env["tenant_id"], ref_type="envelope", ref_id=env["id"])
    await log_event(db, tenant_id=env["tenant_id"], envelope_id=env["id"], signer_id=None, event="counterparty_notified",
                    ip=db.ctx.ip, user_agent=db.ctx.user_agent, detail={"to": to})


def workspace_link() -> str:
    return f"{get_settings().web_origin.rstrip('/')}/agreements"


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
        # A pending MSA sent for signature shows as out for signature; completion accepts it (see public.py).
        await db.run("update agreements set status = :s where id = :id and status in ('draft', 'pending', 'out_for_signature')",
                      {"s": status, "id": env["agreement_id"]})
    if env.get("sow_id"):
        await db.run("update sows set status = :s where id = :id and status in ('draft', 'out_for_signature')",
                      {"s": status, "id": env["sow_id"]})
    if env.get("amendment_id"):
        await db.run("update sow_amendments set status = :s where id = :id and status in ('draft', 'out_for_signature')",
                      {"s": status, "id": env["amendment_id"]})
