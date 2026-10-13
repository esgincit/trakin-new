"""File storage on Supabase Storage (server-side, with the service-role key).

Browsers never get the service key. They upload through the API (small files) or
through a signed upload URL, and read files through short-lived signed URLs.
Without SUPABASE_URL (local development / tests) files are kept on disk instead.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

import httpx

from ..config import get_settings
from ..errors import ApiError

_LOCAL_ROOT = Path(os.environ.get("MYTRAKIN_LOCAL_STORAGE", "/tmp/mytrakin-storage"))

# Vercel Functions accept request and response bodies up to 4.5 MB. Smaller files go through the
# API; larger ones are uploaded by the browser straight to Storage with a signed upload URL.
DIRECT_LIMIT = 4 * 1024 * 1024
MAX_UPLOAD = 25 * 1024 * 1024


def is_remote() -> bool:
    return _remote()


def _remote() -> bool:
    s = get_settings()
    return bool(s.supabase_url and s.supabase_service_role_key)


def _headers() -> dict[str, str]:
    key = get_settings().supabase_service_role_key
    return {"Authorization": f"Bearer {key}", "apikey": key}


def _base() -> str:
    return f"{get_settings().supabase_url.rstrip('/')}/storage/v1"


async def upload(bucket: str, path: str, data: bytes, content_type: str, upsert: bool = False) -> str:
    if not _remote():
        target = _LOCAL_ROOT / bucket / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return path
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{_base()}/object/{bucket}/{quote(path)}",
            headers={**_headers(), "Content-Type": content_type, "x-upsert": "true" if upsert else "false"},
            content=data,
        )
    if response.status_code >= 300:
        raise ApiError(502, "storage_error", "The file could not be stored. Please try again.")
    return path


async def download(bucket: str, path: str) -> bytes:
    if not _remote():
        target = _LOCAL_ROOT / bucket / path
        if not target.exists():
            raise ApiError(404, "not_found", "File not found")
        return target.read_bytes()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{_base()}/object/{bucket}/{quote(path)}", headers=_headers())
    if response.status_code == 404:
        raise ApiError(404, "not_found", "File not found")
    response.raise_for_status()
    return response.content


async def signed_url(bucket: str, path: str, expires_in: int = 300) -> str:
    """A link that works for `expires_in` seconds (default 5 minutes)."""
    if not _remote():
        return f"file://{_LOCAL_ROOT / bucket / path}"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(f"{_base()}/object/sign/{bucket}/{quote(path)}", headers=_headers(),
                                     json={"expiresIn": expires_in})
    response.raise_for_status()
    return f"{get_settings().supabase_url.rstrip('/')}/storage/v1{response.json()['signedURL']}"


def public_url(bucket: str, path: str) -> str:
    if not _remote():
        return f"file://{_LOCAL_ROOT / bucket / path}"
    return f"{_base()}/object/public/{bucket}/{quote(path)}"


async def signed_upload_url(bucket: str, path: str) -> str | None:
    """A one-time URL the browser can PUT the file to (valid 2 hours). None in local development."""
    if not _remote():
        return None
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(f"{_base()}/object/upload/sign/{bucket}/{quote(path)}", headers=_headers(), json={})
    if response.status_code >= 300:
        raise ApiError(502, "storage_error", "Couldn't prepare the upload. Please try again.")
    return f"{_base()}{response.json()['url']}"


def write_local(bucket: str, path: str, data: bytes) -> None:
    target = _LOCAL_ROOT / bucket / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
