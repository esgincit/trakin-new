"""The professional network: LinkedIn-style profiles with photos, connections, posts and
direct messages. Profiles belong to the person and travel with them across workspaces."""

from __future__ import annotations

import secrets
from typing import Any
from uuid import UUID

import orjson
from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field, HttpUrl

from ..deps import TenantDb, member_db
from ..errors import bad_request, conflict, forbidden, not_found
from ..services import storage

router = APIRouter(prefix="/network", tags=["network"])

IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_IMAGE_BYTES = 4 * 1024 * 1024    # stays under Vercel's 4.5 MB request limit


def _photo(path: str | None) -> str | None:
    return storage.public_url("avatars", path) if path else None


def _card(row: dict) -> dict:
    row["avatar_url"] = _photo(row.pop("avatar_path", None))
    if "cover_path" in row:
        row["cover_url"] = _photo(row.pop("cover_path"))
    return row


# ============================================================================ profiles
class ExperienceItem(BaseModel):
    title: str = Field(max_length=120)
    company: str = Field(max_length=120)
    start: str | None = Field(None, max_length=20)
    end: str | None = Field(None, max_length=20)
    description: str | None = Field(None, max_length=2000)


class EducationItem(BaseModel):
    school: str = Field(max_length=160)
    degree: str | None = Field(None, max_length=160)
    year: str | None = Field(None, max_length=10)


class CertificationItem(BaseModel):
    name: str = Field(max_length=160)
    issuer: str | None = Field(None, max_length=120)
    year: str | None = Field(None, max_length=10)


class ProfileIn(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=120)
    headline: str | None = Field(None, max_length=160)
    location: str | None = Field(None, max_length=120)
    about: str | None = Field(None, max_length=3000)
    phone: str | None = Field(None, max_length=30)
    website: HttpUrl | None = None
    open_to_work: bool | None = None
    visibility: str | None = Field(None, pattern="^(network|company_and_connections|company)$")
    show_contact: bool | None = None
    skills: list[str] | None = Field(None, max_length=50)
    experience: list[ExperienceItem] | None = Field(None, max_length=30)
    certifications: list[CertificationItem] | None = Field(None, max_length=30)
    education: list[EducationItem] | None = Field(None, max_length=10)
    preferences: dict[str, Any] | None = None       # theme, density, default list/card view, time zone ...
    notifications: dict[str, Any] | None = None     # which e-mails the person wants


JSON_FIELDS = {"skills", "experience", "certifications", "education", "preferences", "notifications"}


@router.get("/me")
async def my_profile(db: TenantDb = Depends(member_db)):
    row = await db.one("select * from profiles where id = :u", {"u": db.ctx.user_id})
    if row is None:
        raise not_found("Profile")
    return _card(row)


@router.patch("/me")
async def update_profile(body: ProfileIn, db: TenantDb = Depends(member_db)):
    fields = body.model_dump(exclude_unset=True, mode="json")
    if not fields:
        raise bad_request("Nothing to change")
    sets, params = [], {"u": db.ctx.user_id}
    for key, value in fields.items():
        if key in JSON_FIELDS:
            sets.append(f"{key} = cast(:{key} as jsonb)")
            params[key] = orjson.dumps(value).decode()
        else:
            sets.append(f"{key} = :{key}")
            params[key] = value
    return _card(await db.one(f"update profiles set {', '.join(sets)} where id = :u returning *", params))


@router.post("/me/photo")
async def upload_photo(kind: str = Query("avatar", pattern="^(avatar|cover)$"), file: UploadFile = File(),
                       db: TenantDb = Depends(member_db)):
    """Profile photo or cover image (JPEG, PNG or WebP, up to 4 MB)."""
    ext = IMAGE_TYPES.get(file.content_type or "")
    if ext is None:
        raise bad_request("Use a JPEG, PNG or WebP image")
    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise bad_request("The image is larger than 4 MB")
    if not _looks_like_image(data):
        raise bad_request("That file isn't a valid image")
    # Unguessable name, so the public bucket doesn't let anyone list or guess photos.
    path = f"{db.ctx.user_id}/{kind}-{secrets.token_hex(8)}.{ext}"
    await storage.upload("avatars", path, data, file.content_type or "image/jpeg")
    column = "avatar_path" if kind == "avatar" else "cover_path"
    await db.run(f"update profiles set {column} = :p where id = :u", {"p": path, "u": db.ctx.user_id})
    return {"url": _photo(path)}


@router.delete("/me/photo")
async def remove_photo(kind: str = Query("avatar", pattern="^(avatar|cover)$"), db: TenantDb = Depends(member_db)):
    column = "avatar_path" if kind == "avatar" else "cover_path"
    await db.run(f"update profiles set {column} = null where id = :u", {"u": db.ctx.user_id})
    return {"removed": kind}


def _looks_like_image(data: bytes) -> bool:
    return data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG\r\n\x1a\n") or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")


@router.get("/people")
async def people(db: TenantDb = Depends(member_db), q: str | None = None, open_to_work: bool | None = None,
                 limit: int = Query(30, ge=1, le=100)):
    """Search people by name, headline, skill or location."""
    rows = await db.all(
        """select p.id, p.full_name, p.headline, p.location, p.avatar_path, p.open_to_work, p.skills,
                  (select c.status from connections c where (c.requester_id = :u and c.addressee_id = p.id)
                                                          or (c.addressee_id = :u and c.requester_id = p.id)) as connection
             from profiles p
            where p.id <> :u and mytrakin.visible_profile(p.id)
              and (cast(:q as text) is null or p.full_name ilike '%' || :q || '%' or p.headline ilike '%' || :q || '%'
                   or p.location ilike '%' || :q || '%' or p.skills::text ilike '%' || :q || '%')
              and (cast(:otw as boolean) is null or p.open_to_work = :otw)
            order by p.full_name limit :lim""",
        {"u": db.ctx.user_id, "q": q, "otw": open_to_work, "lim": limit})
    return [_card(r) for r in rows]


@router.get("/people/{person_id}")
async def person(person_id: UUID, db: TenantDb = Depends(member_db)):
    if not await db.val("select mytrakin.visible_profile(:p)", {"p": person_id}):
        raise not_found("Profile")
    row = await db.one(
        """select id, full_name, headline, location, about, avatar_path, cover_path, open_to_work, skills, experience,
                  certifications, education, website, show_contact, email, phone
             from profiles where id = :p""", {"p": person_id})
    connection = await db.one(
        """select status, requester_id = :u as i_asked from connections
            where (requester_id = :u and addressee_id = :p) or (requester_id = :p and addressee_id = :u)""",
        {"u": db.ctx.user_id, "p": person_id})
    connected = connection is not None and connection["status"] == "accepted"
    if not (row.pop("show_contact") and connected) and person_id != db.ctx.user_id:
        row["email"] = row["phone"] = None
    row["connection"] = connection
    row["shared_workspaces"] = [r["s"] for r in await db.all("select s from mytrakin.shared_workspaces(:p) s", {"p": person_id})]
    row["connections"] = await db.val(
        "select count(*) from connections where status = 'accepted' and :p in (requester_id, addressee_id)", {"p": person_id})
    return _card(row)


# ============================================================================ connections
@router.get("/connections")
async def connections(db: TenantDb = Depends(member_db)):
    rows = await db.all(
        """select c.status, c.created_at, c.requester_id = :u as outgoing,
                  p.id, p.full_name, p.headline, p.avatar_path
             from connections c join profiles p on p.id = case when c.requester_id = :u then c.addressee_id else c.requester_id end
            where :u in (c.requester_id, c.addressee_id) and c.status <> 'declined'
            order by c.status, p.full_name""", {"u": db.ctx.user_id})
    rows = [_card(r) for r in rows]
    return {
        "connections": [r for r in rows if r["status"] == "accepted"],
        "incoming": [r for r in rows if r["status"] == "pending" and not r["outgoing"]],
        "outgoing": [r for r in rows if r["status"] == "pending" and r["outgoing"]],
    }


@router.post("/connections/{person_id}", status_code=201)
async def connect(person_id: UUID, db: TenantDb = Depends(member_db)):
    if person_id == db.ctx.user_id:
        raise bad_request("You can't connect with yourself")
    if not await db.val("select mytrakin.visible_profile(:p)", {"p": person_id}):
        raise not_found("Profile")
    reverse = await db.one("select status from connections where requester_id = :p and addressee_id = :u",
                           {"p": person_id, "u": db.ctx.user_id})
    if reverse and reverse["status"] == "pending":      # they already asked: accept instead
        await db.run("update connections set status = 'accepted' where requester_id = :p and addressee_id = :u",
                     {"p": person_id, "u": db.ctx.user_id})
        return {"status": "accepted"}
    if reverse and reverse["status"] == "accepted":
        raise conflict("You're already connected")
    if reverse:                                          # an old declined request in the other direction
        await db.run("delete from connections where requester_id = :p and addressee_id = :u", {"p": person_id, "u": db.ctx.user_id})
    await db.run("""insert into connections (requester_id, addressee_id) values (:u, :p)
                    on conflict (requester_id, addressee_id) do update set status = 'pending' where connections.status = 'declined'""",
                 {"u": db.ctx.user_id, "p": person_id})
    return {"status": "pending"}


@router.post("/connections/{person_id}/respond")
async def respond(person_id: UUID, accept: bool = Query(), db: TenantDb = Depends(member_db)):
    if await db.run("""update connections set status = :s where requester_id = :p and addressee_id = :u and status = 'pending'""",
                    {"s": "accepted" if accept else "declined", "p": person_id, "u": db.ctx.user_id}) == 0:
        raise not_found("Invitation")
    return {"status": "accepted" if accept else "declined"}


@router.delete("/connections/{person_id}")
async def disconnect(person_id: UUID, db: TenantDb = Depends(member_db)):
    await db.run("""delete from connections where (requester_id = :u and addressee_id = :p) or (requester_id = :p and addressee_id = :u)""",
                 {"u": db.ctx.user_id, "p": person_id})
    return {"removed": True}


# ============================================================================ posts
class PostIn(BaseModel):
    body: str = Field(min_length=1, max_length=3000)
    kind: str = Field("update", pattern="^(update|kudos|announcement|opening)$")
    audience: str = Field("company", pattern="^(company|network)$")


@router.get("/feed")
async def feed(db: TenantDb = Depends(member_db), before: str | None = None, limit: int = Query(30, ge=1, le=100)):
    """Posts from this workspace plus network-wide posts from people you can see. Newest first."""
    rows = await db.all(
        """select po.id, po.kind, po.body, po.likes, po.created_at, po.tenant_id is null as network_wide,
                  p.id as author_id, p.full_name as author, p.headline, p.avatar_path, po.author_id = :u as mine
             from posts po join profiles p on p.id = po.author_id
            where (po.tenant_id is not null or mytrakin.visible_profile(po.author_id))
              and (cast(:before as timestamptz) is null or po.created_at < cast(:before as timestamptz))
            order by po.created_at desc limit :lim""", {"u": db.ctx.user_id, "before": before, "lim": limit})
    return [_card(r) for r in rows]


@router.post("/posts", status_code=201)
async def post(body: PostIn, db: TenantDb = Depends(member_db)):
    if body.kind == "announcement" and not db.ctx.allows("hr"):
        raise forbidden("Only HR and admins can post announcements")
    if db.ctx.tenant_id is None and body.audience == "company":
        raise bad_request("You're not in a company yet, so post to “Everyone in my network”.")
    return await db.one(
        "insert into posts (tenant_id, author_id, kind, body) values (:t, :u, :k, :b) returning *",
        {"t": db.ctx.tenant_id if body.audience == "company" else None, "u": db.ctx.user_id, "k": body.kind, "b": body.body.strip()})


@router.post("/posts/{post_id}/like")
async def like(post_id: UUID, db: TenantDb = Depends(member_db)):
    likes = await db.val("update posts set likes = likes + 1 where id = :id returning likes", {"id": post_id})
    if likes is None:
        raise not_found("Post")
    return {"likes": likes}


@router.delete("/posts/{post_id}")
async def delete_post(post_id: UUID, db: TenantDb = Depends(member_db)):
    if await db.run("delete from posts where id = :id", {"id": post_id}) == 0:
        raise not_found("Post")
    return {"deleted": True}


# ============================================================================ messages
class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


@router.get("/messages")
async def threads(db: TenantDb = Depends(member_db)):
    """One row per conversation with the latest message and unread count."""
    rows = await db.all(
        """select distinct on (other) other as person_id, p.full_name, p.headline, p.avatar_path, m.body as last_message,
                  m.created_at as last_at,
                  (select count(*) from messages u where u.sender_id = other and u.recipient_id = :u and u.read_at is null) as unread
             from (select *, case when sender_id = :u then recipient_id else sender_id end as other from messages) m
             join profiles p on p.id = m.other
            order by other, m.created_at desc""", {"u": db.ctx.user_id})
    rows.sort(key=lambda r: r["last_at"], reverse=True)
    return [_card(r) for r in rows]


@router.get("/messages/{person_id}")
async def conversation(person_id: UUID, db: TenantDb = Depends(member_db), limit: int = Query(100, ge=1, le=500)):
    rows = await db.all(
        """select id, sender_id, body, created_at, read_at, sender_id = :u as mine from messages
            where (sender_id = :u and recipient_id = :p) or (sender_id = :p and recipient_id = :u)
            order by created_at desc limit :lim""", {"u": db.ctx.user_id, "p": person_id, "lim": limit})
    await db.run("update messages set read_at = now() where sender_id = :p and recipient_id = :u and read_at is null",
                 {"u": db.ctx.user_id, "p": person_id})
    return list(reversed(rows))


@router.post("/messages/{person_id}", status_code=201)
async def send_message(person_id: UUID, body: MessageIn, db: TenantDb = Depends(member_db)):
    """Message anyone whose profile you can see (colleagues, connections, consultants at other companies)."""
    if person_id == db.ctx.user_id:
        raise bad_request("You can't message yourself")
    if not await db.val("select mytrakin.visible_profile(:p)", {"p": person_id}):
        raise not_found("Profile")
    return await db.one(
        "insert into messages (sender_id, recipient_id, body) values (:u, :p, :b) returning id, body, created_at",
        {"u": db.ctx.user_id, "p": person_id, "b": body.body.strip()})
