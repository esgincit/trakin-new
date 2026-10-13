"""Direct uploads for large files.

Vercel Functions take request bodies up to 4.5 MB, so files above 4 MB skip the API:

    1. POST /uploads            → a one-time signed URL for Supabase Storage (and the storage path)
    2. browser PUTs the file to that URL
    3. POST /files/confirm      (attachments) or POST /envelopes with document_path (e-signatures)

In local development (no Supabase Storage) the URL points at PUT /uploads/local on this API instead.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from ..config import get_settings
from ..deps import TenantDb, tenant_db
from ..errors import ApiError, bad_request, forbidden
from ..services import storage

router = APIRouter(prefix="/uploads", tags=["files"])

OWNER_TYPES = "^(company|consultant|project|agreement|sow|invoice|policy|expense)$"


class UploadIn(BaseModel):
    purpose: Literal["attachment", "esign"]
    filename: str = Field(min_length=1, max_length=200)
    content_type: str = Field(max_length=120)
    size: int = Field(gt=0, le=storage.MAX_UPLOAD)
    owner_type: str | None = Field(None, pattern=OWNER_TYPES)
    owner_id: UUID | None = None


def safe_name(filename: str) -> str:
    keep = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in filename)
    return keep[-120:] or "file"


def can_attach(ctx, owner_type: str, owner_id: UUID) -> bool:
    """Same rule as the documents_upload policy, checked before handing out an upload URL."""
    if ctx.internal:
        return True
    if ctx.role == "consultant":
        return owner_type == "expense" or (owner_type == "consultant" and owner_id == ctx.consultant_id)
    if ctx.role == "vendor_admin":
        return owner_type == "company" and owner_id == ctx.company_id
    return False


def _local_token(bucket: str, path: str) -> str:
    key = (get_settings().cron_secret or "local-development").encode()
    return hmac.new(key, f"{bucket}/{path}".encode(), hashlib.sha256).hexdigest()


@router.post("")
async def start_upload(body: UploadIn, request: Request, db: TenantDb = Depends(tenant_db)):
    if body.purpose == "esign":
        db.ctx.require("legal", "account_manager", "finance", "hr")
        if body.content_type != "application/pdf":
            raise bad_request("E-signature documents must be PDFs")
        bucket, path = "esign", f"{db.ctx.tenant_id}/uploads/{uuid4()}.pdf"
    else:
        if body.owner_type is None or body.owner_id is None:
            raise bad_request("Say which record the file belongs to")
        if not can_attach(db.ctx, body.owner_type, body.owner_id):
            raise forbidden()
        bucket = "documents"
        path = f"{db.ctx.tenant_id}/{body.owner_type}/{body.owner_id}/{secrets.token_hex(6)}-{safe_name(body.filename)}"

    url = await storage.signed_upload_url(bucket, path)
    if url is None:   # local development
        url = str(request.url_for("local_upload").include_query_params(bucket=bucket, path=path, token=_local_token(bucket, path)))
    return {"upload_url": url, "bucket": bucket, "path": path, "method": "PUT"}


@router.put("/local", name="local_upload", include_in_schema=False)
async def local_upload(request: Request, bucket: str = Query(), path: str = Query(), token: str = Query()):
    """Development stand-in for Supabase's signed upload URL."""
    if storage.is_remote() or get_settings().is_production:
        raise ApiError(404, "not_found", "Not found")
    if not hmac.compare_digest(token, _local_token(bucket, path)):
        raise forbidden("Invalid upload token")
    data = await request.body()
    if len(data) > storage.MAX_UPLOAD:
        raise bad_request("The file is larger than 25 MB")
    storage.write_local(bucket, path, data)
    return {"stored": path}
