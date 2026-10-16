"""Compliance: expiring documents (I-9, passport, EAD, COI ...), policies, registrations
waiting for approval, file attachments, reminder rules and the e-mail log."""

from __future__ import annotations

from datetime import date
from uuid import UUID

import orjson
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from ..deps import TenantDb, tenant_db
from ..errors import bad_request, conflict, forbidden, not_found
from ..services import storage
from ..services.email import render, send_email
from ..utils import sha256_hex

router = APIRouter(tags=["compliance"])

DOC_TYPES = "^(i9_reverification|passport|ead|i94|visa_notice|coi|w9|background_check|certification|drivers_license|agreement|other)$"
MAX_FILE_BYTES = storage.DIRECT_LIMIT       # bigger files use /uploads (direct to storage)


# ============================================================================ tracked documents
class TrackedIn(BaseModel):
    consultant_id: UUID | None = None
    company_id: UUID | None = None
    doc_type: str = Field(pattern=DOC_TYPES)
    label: str = Field(min_length=2, max_length=200)
    expires_on: date | None = None
    status: str = Field("valid", pattern="^(valid|missing|pending|expired|renewed)$")
    blocks: str | None = None
    recipients: list[str] = []


class RenewIn(BaseModel):
    expires_on: date
    note: str | None = None


@router.get("/compliance/documents")
async def tracked_documents(db: TenantDb = Depends(tenant_db), within_days: int | None = None):
    """Everything that expires, soonest first, with how many days are left."""
    return await db.all(
        """select d.*, coalesce(k.full_name, co.name) as owner, k.engagement,
                  (d.expires_on - current_date) as days_left,
                  case when d.status = 'missing' then 'missing'
                       when d.expires_on < current_date then 'expired'
                       when d.expires_on <= current_date + 30 then 'due_30'
                       when d.expires_on <= current_date + 120 then 'due_120'
                       else 'ok' end as urgency
             from tracked_documents d
             left join consultants k on k.id = d.consultant_id
             left join companies co on co.id = d.company_id
            where d.active and (cast(:w as int) is null or d.expires_on <= current_date + cast(:w as int) or d.status = 'missing')
            order by d.status <> 'missing', d.expires_on nulls last""",
        {"w": within_days})


@router.post("/compliance/documents", status_code=201)
async def add_tracked(body: TrackedIn, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("hr", "legal")
    if not body.consultant_id and not body.company_id:
        raise bad_request("Choose the consultant or company this document belongs to")
    return await db.one(
        """insert into tracked_documents (tenant_id, consultant_id, company_id, doc_type, label, expires_on, status, blocks, recipients)
           values (:t, :c, :co, :type, :label, :exp, :status, :blocks, :rcpt) returning *""",
        {"t": db.ctx.tenant_id, "c": body.consultant_id, "co": body.company_id, "type": body.doc_type, "label": body.label,
         "exp": body.expires_on, "status": body.status, "blocks": body.blocks, "rcpt": body.recipients})


@router.post("/compliance/documents/{doc_id}/renew")
async def renew(doc_id: UUID, body: RenewIn, db: TenantDb = Depends(tenant_db)):
    """A new document arrived: record the new expiry date. Reminders restart from it."""
    db.ctx.require("hr", "legal")
    if body.expires_on <= date.today():
        raise bad_request("The new expiry date must be in the future")
    row = await db.one(
        """update tracked_documents set expires_on = :exp, status = 'valid', last_notified_on = null where id = :id returning *""",
        {"exp": body.expires_on, "id": doc_id})
    if row is None:
        raise not_found("Document")
    if row["doc_type"] in ("ead", "i9_reverification") and row["consultant_id"]:
        await db.run("update consultants set work_auth_expires = :exp where id = :c", {"exp": body.expires_on, "c": row["consultant_id"]})
    return row


@router.delete("/compliance/documents/{doc_id}")
async def stop_tracking(doc_id: UUID, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("hr", "legal")
    if await db.run("update tracked_documents set active = false where id = :id", {"id": doc_id}) == 0:
        raise not_found("Document")
    return {"id": doc_id, "active": False}


@router.get("/compliance/work-authorization")
async def work_authorization(db: TenantDb = Depends(tenant_db)):
    """I-9 / E-Verify / work-authorization status for everyone who is not former."""
    db.ctx.require("hr", "legal", "account_manager")
    return await db.all(
        """select c.id, c.full_name, c.engagement, c.status, c.work_auth_type, c.work_auth_expires, c.i9_status, c.everify_status,
                  (c.work_auth_expires - current_date) as days_left, emp.name as employer,
                  case when et.pay_model = 'vendor' then 'Employer (' || coalesce(emp.name, 'vendor') || ') is responsible for Form I-9'
                       when et.pay_model = 'self' then 'Not an employee — no Form I-9'
                       when c.i9_status is null then 'Form I-9 not recorded'
                       when c.work_auth_expires < current_date then 'Work authorization expired — stop work and reverify'
                       when c.work_auth_expires <= current_date + 90 then 'Reverification due within 90 days'
                       else 'OK' end as finding
             from consultants c left join companies emp on emp.id = c.employer_company_id
             join engagement_types et on et.code = c.engagement
            where c.status <> 'former'
            order by c.work_auth_expires nulls last""")


# ============================================================================ policies
@router.get("/policies")
async def list_policies(db: TenantDb = Depends(tenant_db)):
    rows = await db.all(
        """select po.*,
                  (select count(*) from policy_acceptances pa where pa.policy_id = po.id) as accepted,
                  (select count(*) from consultants c where c.status = 'active' and c.engagement = any (po.applies_to)) as expected
             from policies po order by po.active desc, po.name, po.effective_on desc""")
    if not db.ctx.internal:
        for r in rows:
            r.pop("accepted")
            r.pop("expected")
    return rows


@router.post("/policies", status_code=201)
async def add_policy(
    db: TenantDb = Depends(tenant_db),
    name: str = Form(min_length=2, max_length=200),
    version: str = Form(min_length=1, max_length=20),
    effective_on: date = Form(),
    applies_to: str = Form("w2_fulltime,w2_contract,c2c,e2e,1099", description="Comma-separated engagement types"),
    file: UploadFile | None = File(None),
):
    """Publish a policy (or a new version). Older versions of the same policy are retired."""
    db.ctx.require("hr", "legal")
    groups = [g.strip() for g in applies_to.split(",") if g.strip()]
    known = {r["code"] for r in await db.all("select code from engagement_types where is_active")}
    if not groups or any(g not in known for g in groups):
        raise bad_request(f"applies_to must list engagement types from: {', '.join(sorted(known))}")
    path = None
    if file is not None:
        data = await file.read()
        if len(data) > MAX_FILE_BYTES:
            raise bad_request("Policy PDFs can be at most 4 MB — compress the PDF and try again")
        path = f"{db.ctx.tenant_id}/policies/{name.lower().replace(' ', '-')}-{version}.pdf"
        await storage.upload("documents", path, data, file.content_type or "application/pdf", upsert=True)
    await db.run("update policies set active = false where name = :n and active", {"n": name})
    return await db.one(
        """insert into policies (tenant_id, name, version, effective_on, applies_to, file_path)
           values (:t, :n, :v, :eff, :groups, :path) returning *""",
        {"t": db.ctx.tenant_id, "n": name, "v": version, "eff": effective_on, "groups": groups, "path": path})


@router.get("/policies/{policy_id}/acceptances")
async def acceptances(policy_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Who accepted (with time and IP address) and who still needs to."""
    if not db.ctx.internal:
        raise forbidden()
    return await db.all(
        """select c.id as consultant_id, c.full_name, c.engagement, pa.accepted_at, pa.ip, pa.user_agent
             from policies po
             join consultants c on c.status = 'active' and c.engagement = any (po.applies_to)
             left join policy_acceptances pa on pa.policy_id = po.id and pa.consultant_id = c.id
            where po.id = :id order by pa.accepted_at nulls first, c.full_name""", {"id": policy_id})


@router.get("/policies/{policy_id}/file")
async def policy_file(policy_id: UUID, db: TenantDb = Depends(tenant_db)):
    path = await db.val("select file_path from policies where id = :id", {"id": policy_id})
    if not path:
        raise not_found("Policy file")
    return {"url": await storage.signed_url("documents", path)}


# ============================================================================ registrations
class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected|needs_info)$")
    note: str | None = Field(None, max_length=1000)


@router.get("/registrations")
async def registrations(db: TenantDb = Depends(tenant_db), status: str | None = None):
    db.ctx.require("legal", "hr", "account_manager")
    return await db.all(
        """select r.*, (select count(*) from documents d where d.owner_type = 'registration' and d.owner_id = r.id) as files
             from registrations r where (cast(:s as text) is null or r.status = :s)
            order by r.status <> 'pending', r.created_at desc""", {"s": status})


@router.get("/registrations/{reg_id}")
async def registration(reg_id: UUID, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("legal", "hr", "account_manager")
    reg = await db.one("select * from registrations where id = :id", {"id": reg_id})
    if reg is None:
        raise not_found("Registration")
    reg["files"] = await db.all(
        "select id, name, size_bytes, mime_type, created_at from documents where owner_type = 'registration' and owner_id = :id",
        {"id": reg_id})
    reg["duplicates"] = await db.all(
        """select 'company' as kind, id, name from companies where lower(name) = lower(:n) or (ein is not null and ein = :ein)
           union all
           select 'consultant', id, full_name from consultants where email = :e""",
        {"n": reg["name"], "ein": reg["ein"], "e": reg["email"]})
    return reg


@router.post("/registrations/{reg_id}/decision")
async def decide(reg_id: UUID, body: DecisionIn, db: TenantDb = Depends(tenant_db)):
    """Approve (creates the company or the consultant, starting onboarding), reject, or ask for more information."""
    db.ctx.require("legal", "hr", "account_manager")
    reg = await db.one("select * from registrations where id = :id for update", {"id": reg_id})
    if reg is None:
        raise not_found("Registration")
    if reg["status"] in ("approved", "rejected"):
        raise conflict(f"This registration was already {reg['status']}")
    if body.decision in ("rejected", "needs_info") and not body.note:
        raise bad_request("Add a note so the applicant knows why")

    created = None
    if body.decision == "approved":
        if reg["kind"] in ("client", "vendor"):
            created = await db.one(
                """insert into companies (tenant_id, name, kind, kinds, ein, state, contact_name, contact_email, contact_phone, status, onboarding_stage)
                   values (:t, :n, :k, cast(array[:k] as text[]), :ein, :s, :c, :e, :p, 'onboarding', 2) returning id, name""",
                {"t": db.ctx.tenant_id, "n": reg["name"], "k": reg["kind"], "ein": reg["ein"], "s": reg["state"],
                 "c": reg["contact"], "e": reg["email"], "p": reg["phone"]})
            await db.run("update documents set owner_type = 'company', owner_id = :c where owner_type = 'registration' and owner_id = :r",
                         {"c": created["id"], "r": reg_id})
        else:
            from .consultants import CHECKLISTS

            engagement = "1099" if reg["kind"] == "1099" else "w2_contract"
            checklist = [{"item": item, "done": False} for item in CHECKLISTS[engagement]]
            created = await db.one(
                """insert into consultants (tenant_id, full_name, email, phone, engagement, status, start_date, onboarding_checklist)
                   values (:t, :n, :e, :p, :eng, 'onboarding', current_date, cast(:cl as jsonb)) returning id, full_name as name""",
                {"t": db.ctx.tenant_id, "n": reg["contact"] if reg["kind"] == "consultant" else reg["name"], "e": reg["email"],
                 "p": reg["phone"], "eng": engagement, "cl": orjson.dumps(checklist).decode()})
            await db.run("update documents set owner_type = 'consultant', owner_id = :c where owner_type = 'registration' and owner_id = :r",
                         {"c": created["id"], "r": reg_id})

    await db.run("update registrations set status = :s, decided_by = :u, decided_at = now() where id = :id",
                 {"s": body.decision, "u": db.ctx.user_id, "id": reg_id})
    tenant = await db.val("select name from tenants where id = :t", {"t": db.ctx.tenant_id})
    text = {
        "approved": "Your registration is approved. We'll send the agreements to sign next.",
        "rejected": f"We can't approve this registration. {body.note or ''}",
        "needs_info": f"We need a little more information: {body.note or ''}",
    }[body.decision]
    await send_email(db, to=reg["email"], subject=f"{tenant}: registration {body.decision.replace('_', ' ')}", kind="registration",
                     tenant_id=db.ctx.tenant_id, ref_type="registration", ref_id=reg_id,
                     html_body=render(f"Registration with {tenant}", [text]))
    return {"id": reg_id, "status": body.decision, "created": created}


# ============================================================================ attachments
OWNER_TYPES = "^(company|consultant|project|agreement|sow|invoice|policy|expense)$"


@router.get("/files")
async def list_files(owner_type: str, owner_id: UUID, db: TenantDb = Depends(tenant_db)):
    return await db.all(
        """select d.id, d.name, d.mime_type, d.size_bytes, d.created_at, p.full_name as uploaded_by
             from documents d left join profiles p on p.id = d.uploaded_by
            where d.owner_type = :t and d.owner_id = :o and d.deleted_at is null order by d.created_at desc""",
        {"t": owner_type, "o": owner_id})


@router.post("/files", status_code=201)
async def upload_file(
    db: TenantDb = Depends(tenant_db),
    owner_type: str = Form(pattern=OWNER_TYPES),
    owner_id: UUID = Form(),
    file: UploadFile = File(),
):
    """Attach a file up to 4 MB to a company, consultant, project, contract or invoice.
    Larger files (up to 25 MB): POST /uploads, PUT the file, then POST /files/confirm."""
    data = await file.read()
    if not data:
        raise bad_request("The file is empty")
    if len(data) > MAX_FILE_BYTES:
        raise bad_request("Files over 4 MB are uploaded directly — refresh the page and try again", "use_direct_upload")
    name = (file.filename or "file").replace("/", "_")[-150:]
    path = f"{db.ctx.tenant_id}/{owner_type}/{owner_id}/{sha256_hex(data)[:12]}-{name}"
    await storage.upload("documents", path, data, file.content_type or "application/octet-stream", upsert=True)
    return await db.one(
        """insert into documents (tenant_id, owner_type, owner_id, name, storage_path, mime_type, size_bytes, sha256, uploaded_by)
           values (:t, :ot, :o, :n, :p, :m, :s, :h, :u) returning id, name, mime_type, size_bytes, created_at""",
        {"t": db.ctx.tenant_id, "ot": owner_type, "o": owner_id, "n": name, "p": path, "m": file.content_type,
         "s": len(data), "h": sha256_hex(data), "u": db.ctx.user_id})


class ConfirmIn(BaseModel):
    owner_type: str = Field(pattern=OWNER_TYPES)
    owner_id: UUID
    path: str = Field(max_length=400)
    name: str = Field(min_length=1, max_length=200)
    content_type: str | None = None


@router.post("/files/confirm", status_code=201)
async def confirm_upload(body: ConfirmIn, db: TenantDb = Depends(tenant_db)):
    """Record a file the browser uploaded straight to storage (see /uploads)."""
    if not body.path.startswith(f"{db.ctx.tenant_id}/{body.owner_type}/{body.owner_id}/") or ".." in body.path:
        raise forbidden("That upload doesn't belong to this record")
    data = await storage.download("documents", body.path)
    if len(data) > storage.MAX_UPLOAD:
        raise bad_request("The file is larger than 25 MB")
    return await db.one(
        """insert into documents (tenant_id, owner_type, owner_id, name, storage_path, mime_type, size_bytes, sha256, uploaded_by)
           values (:t, :ot, :o, :n, :p, :m, :s, :h, :u) returning id, name, mime_type, size_bytes, created_at""",
        {"t": db.ctx.tenant_id, "ot": body.owner_type, "o": body.owner_id, "n": body.name.replace("/", "_")[-150:], "p": body.path,
         "m": body.content_type, "s": len(data), "h": sha256_hex(data), "u": db.ctx.user_id})


@router.get("/files/{file_id}/link")
async def file_link(file_id: UUID, db: TenantDb = Depends(tenant_db)):
    doc = await db.one("select storage_path, name from documents where id = :id and deleted_at is null", {"id": file_id})
    if doc is None:
        raise not_found("File")
    return {"url": await storage.signed_url("documents", doc["storage_path"]), "name": doc["name"]}


@router.delete("/files/{file_id}")
async def remove_file(file_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Soft delete: hidden at once, purged after 30 days, and the removal is in the audit log."""
    if await db.run("update documents set deleted_at = now() where id = :id and deleted_at is null", {"id": file_id}) == 0:
        raise not_found("File")
    return {"id": file_id, "deleted": True}


# ============================================================================ reminders & e-mail log
class RuleIn(BaseModel):
    offsets: list[int] | None = None
    channels: list[str] | None = None
    enabled: bool | None = None


@router.get("/reminder-rules")
async def reminder_rules(db: TenantDb = Depends(tenant_db)):
    return await db.all("select * from reminder_rules order by area, key")


@router.patch("/reminder-rules/{rule_id}")
async def update_rule(rule_id: UUID, body: RuleIn, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("tenant_admin")
    fields = body.model_dump(exclude_unset=True)
    if "channels" in fields and any(c not in {"email", "sms", "in_app"} for c in fields["channels"]):
        raise bad_request("Channels can be email, sms or in_app")
    if not fields:
        raise bad_request("Nothing to change")
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    row = await db.one(f"update reminder_rules set {sets} where id = :id returning *", {**fields, "id": rule_id})
    if row is None:
        raise not_found("Reminder rule")
    return row


@router.get("/notifications")
async def notification_log(db: TenantDb = Depends(tenant_db), kind: str | None = None, limit: int = 200):
    return await db.all(
        """select * from notifications where (cast(:k as text) is null or kind = :k)
            order by sent_at desc limit :lim""", {"k": kind, "lim": min(max(limit, 1), 1000)})
