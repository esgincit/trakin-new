"""Workspace administration: users and roles, the audit log, and workspace settings."""

from __future__ import annotations

import secrets
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
import orjson
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field

from ..config import get_settings
from ..deps import TenantDb, tenant_db
from ..errors import bad_request, conflict, forbidden, not_found
from ..services import numbering, workflow
from ..services.email import render, send_email

router = APIRouter(tags=["administration"])

ROLES = "^(tenant_admin|finance|account_manager|legal|hr|approver|viewer|vendor_admin|client_user|consultant)$"


# ============================================================================ users
class InviteIn(BaseModel):
    email: EmailStr
    role: str = Field(pattern=ROLES)
    title: str | None = None
    company_id: UUID | None = None         # vendor_admin / client_user
    consultant_id: UUID | None = None      # consultant
    manager_id: UUID | None = None
    signing_limit: Decimal | None = Field(None, ge=0)
    create_login: bool = False             # also make a confirmed password login (no e-mail needed)


class MembershipPatch(BaseModel):
    role: str | None = Field(None, pattern=ROLES)
    title: str | None = None
    manager_id: UUID | None = None
    signing_limit: Decimal | None = Field(None, ge=0)
    status: str | None = Field(None, pattern="^(active|locked|deactivated)$")


@router.get("/users")
async def list_users(db: TenantDb = Depends(tenant_db)):
    if not db.ctx.internal:
        raise forbidden()
    return await db.all(
        """select m.id, m.user_id, uc.code as user_code, coalesce(p.email, m.invited_email) as email, p.full_name, p.avatar_path, m.role, m.title,
                  m.status, m.last_active_at, m.signing_limit, m.created_at, mgr.full_name as manager, m.manager_id,
                  co.name as company, k.full_name as consultant
             from memberships m
             left join profiles p on p.id = m.user_id
             left join user_codes uc on uc.user_id = m.user_id
             left join memberships mm on mm.id = m.manager_id left join profiles mgr on mgr.id = mm.user_id
             left join companies co on co.id = m.company_id
             left join consultants k on k.id = m.consultant_id
            order by m.status, m.role, coalesce(p.full_name, m.invited_email::text)""")


@router.post("/users", status_code=201)
async def invite(body: InviteIn, db: TenantDb = Depends(tenant_db)):
    """Invite someone. They sign in with this e-mail (code, SSO or password) and land in this workspace.

    With create_login, their password login is made right away (confirmed, no e-mail
    needed) and the temporary password is e-mailed to them plus returned once here.
    """
    db.ctx.require("tenant_admin")
    if body.role in ("vendor_admin", "client_user") and body.company_id is None:
        raise bad_request("Choose the company this person represents")
    if body.role == "consultant" and body.consultant_id is None:
        raise bad_request("Choose the consultant record this login belongs to")

    temp_password: str | None = None
    existing_user = await db.val("select id from profiles where email = :e", {"e": body.email})
    if body.create_login:
        temp_password = await _provision_login(str(body.email), existing_user)
        if existing_user is None:
            existing_user = await db.val("select id from profiles where email = :e", {"e": body.email})
    if existing_user and await db.val("select 1 from memberships where user_id = :u", {"u": existing_user}):
        raise conflict("This person is already a user in this workspace")
    row = await db.one(
        """insert into memberships (tenant_id, user_id, invited_email, role, title, company_id, consultant_id, manager_id,
                                    signing_limit, status)
           values (:t, :u, :e, :r, :title, :co, :con, :mgr, :lim, :status)
           on conflict (tenant_id, invited_email) where user_id is null
           do update set role = excluded.role, title = excluded.title, company_id = excluded.company_id,
                         consultant_id = excluded.consultant_id, manager_id = excluded.manager_id, signing_limit = excluded.signing_limit
           returning id, status""",
        {"t": db.ctx.tenant_id, "u": existing_user, "e": None if existing_user else body.email, "r": body.role,
         "title": body.title, "co": body.company_id, "con": body.consultant_id, "mgr": body.manager_id,
         "lim": body.signing_limit, "status": "active" if existing_user else "invited"})

    tenant = await db.val("select name from tenants where id = :t", {"t": db.ctx.tenant_id})
    login = f"{get_settings().web_origin.rstrip('/')}/login?email={body.email}"
    if temp_password:
        howto = (f"Your temporary password is {temp_password}. Sign in with this e-mail address and choose "
                 "\"Use a password\", then change it under Account & security.")
    else:
        howto = ("Sign in with this e-mail address — we'll send you a one-time code, or use your "
                 "company's single sign-on if it is set up.")
    await send_email(db, to=body.email, subject=f"You're invited to {tenant} on myTrakIn", kind="invite",
                     tenant_id=db.ctx.tenant_id, ref_type="membership", ref_id=row["id"],
                     html_body=render(f"Join {tenant} on myTrakIn",
                                      [f"You've been invited as {body.role.replace('_', ' ')}.", howto],
                                      button=("Sign in", login)))
    if temp_password:
        return {**row, "login_created": True, "temp_password": temp_password}
    return row


async def _provision_login(email: str, user_id: UUID | None) -> str:
    """Create a confirmed password login through the Supabase Auth Admin API (sends no e-mail).

    Someone who already started signing up is confirmed and given a fresh temporary
    password instead. Returns the temporary password.
    """
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise bad_request("Password setup needs SUPABASE_SERVICE_ROLE_KEY on the API — send the invitation instead")
    temp_password = "Tmp-" + secrets.token_urlsafe(12)
    base = f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users"
    headers = {"apikey": settings.supabase_service_role_key,
               "Authorization": f"Bearer {settings.supabase_service_role_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            if user_id is None:
                created = await client.post(base, headers=headers,
                                            json={"email": email, "password": temp_password, "email_confirm": True})
                if created.status_code in (200, 201):
                    return temp_password
            else:
                updated = await client.put(f"{base}/{user_id}", headers=headers,
                                           json={"email_confirm": True, "password": temp_password})
                if updated.status_code == 200:
                    return temp_password
            raise bad_request("Couldn't create their login — they may already have one; ask them to sign in")
    except httpx.HTTPError as exc:
        raise bad_request("Couldn't reach sign-in to create their login — try again") from exc


@router.patch("/users/{membership_id}")
async def update_user(membership_id: UUID, body: MembershipPatch, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("tenant_admin")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise bad_request("Nothing to change")
    if membership_id == db.ctx.membership_id and (fields.get("role", "tenant_admin") != "tenant_admin"
                                                  or fields.get("status", "active") != "active"):
        raise bad_request("You can't remove your own admin access — ask another admin")
    target = await db.one("select role from memberships where id = :id", {"id": membership_id})
    if target is None:
        raise not_found("User")
    if target["role"] == "tenant_admin" and (fields.get("role", "tenant_admin") != "tenant_admin"
                                             or fields.get("status", "active") != "active"):
        admins = await db.val("select count(*) from memberships where role = 'tenant_admin' and status = 'active'")
        if admins <= 1:
            raise bad_request("A workspace needs at least one active admin")
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    return await db.one(f"update memberships set {sets} where id = :id returning *", {**fields, "id": membership_id})


@router.delete("/users/{membership_id}")
async def cancel_invite(membership_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Withdraw an invitation that hasn't been accepted. Active users are deactivated instead (history is kept)."""
    db.ctx.require("tenant_admin")
    if await db.run("delete from memberships where id = :id and user_id is null", {"id": membership_id}) == 0:
        raise conflict("Only pending invitations can be withdrawn. Deactivate active users instead.")
    return {"id": membership_id, "deleted": True}


# ============================================================================ audit
@router.get("/audit")
async def audit(
    db: TenantDb = Depends(tenant_db),
    entity: str | None = None,
    entity_id: str | None = None,
    actor: UUID | None = None,
    action: str | None = Query(None, pattern="^(insert|update|delete)$"),
    since: date | None = None,
    until: date | None = None,
    q: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    before_id: int | None = None,
):
    """Who changed what, when, and from which IP address. Newest first; page with `before_id`."""
    db.ctx.require("legal", "finance")
    return await db.all(
        """select a.id, a.at, a.actor_id, coalesce(p.full_name, initcap(a.actor_role)) as actor, a.actor_role, a.action,
                  a.entity, a.entity_id, a.changes, a.ip, a.user_agent
             from audit_log a left join profiles p on p.id = a.actor_id
            where (cast(:entity as text) is null or a.entity = :entity)
              and (cast(:eid as text) is null or a.entity_id = :eid)
              and (cast(:actor as uuid) is null or a.actor_id = :actor)
              and (cast(:action as text) is null or a.action = :action)
              and (cast(:since as date) is null or a.at >= :since)
              and (cast(:until as date) is null or a.at < cast(:until as date) + 1)
              and (cast(:q as text) is null or a.changes::text ilike '%' || :q || '%' or p.full_name ilike '%' || :q || '%')
              and (cast(:before as bigint) is null or a.id < :before)
            order by a.id desc limit :lim""",
        {"entity": entity, "eid": entity_id, "actor": actor, "action": action, "since": since, "until": until,
         "q": q, "before": before_id, "lim": limit})


# ============================================================================ workspace
class WorkspaceIn(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    legal_name: str | None = None
    ein: str | None = Field(None, pattern=r"^\d{2}-?\d{7}$")
    state: str | None = Field(None, max_length=2)
    settings: dict[str, Any] | None = None   # sign-in methods, MFA policy, branding, invoice footer ...


@router.get("/workspace")
async def workspace(db: TenantDb = Depends(tenant_db)):
    row = await db.one("select * from tenants where id = :t", {"t": db.ctx.tenant_id})
    if not db.ctx.allows("tenant_admin"):
        row.pop("settings", None)
        row.pop("ein", None)
    return row


@router.get("/workspace/workflow")
async def workspace_workflow(db: TenantDb = Depends(tenant_db)):
    """The workflow switches every gate reads (NDA, MSA, acceptance, resource contract)."""
    if not db.ctx.internal:
        raise forbidden()
    return await workflow.rules(db)


@router.get("/workspace/numbering")
async def workspace_numbering(db: TenantDb = Depends(tenant_db)):
    """Numbering template per entity (saved or default) with the next number each would produce (WF-08)."""
    db.ctx.require("tenant_admin")
    out = {}
    for entity in numbering.DEFAULTS:
        out[entity] = {"template": await numbering.template_for(db, entity),
                       "next": await numbering.preview_code(db, entity, CLIENT="CLIENT", PROJECT="PROJECT")}
    return out


@router.patch("/workspace")
async def update_workspace(body: WorkspaceIn, db: TenantDb = Depends(tenant_db)):
    db.ctx.require("tenant_admin")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise bad_request("Nothing to change")
    if fields.get("settings") and "workflow" in fields["settings"]:
        # The jsonb merge below is shallow; merge the switches here so one change keeps the others.
        fields["settings"]["workflow"] = {**await workflow.rules(db), **workflow.validate(fields["settings"]["workflow"])}
    if fields.get("settings") and "numbering" in fields["settings"]:
        try:
            templates = numbering.validate(fields["settings"]["numbering"])
        except ValueError as exc:
            raise bad_request(str(exc)) from exc
        saved = await db.val("select settings -> 'numbering' from tenants where id = :t", {"t": db.ctx.tenant_id})
        saved = orjson.loads(saved) if isinstance(saved, (str, bytes)) else (saved or {})
        fields["settings"]["numbering"] = {**saved, **templates}
    params: dict[str, Any] = {"t": db.ctx.tenant_id}
    sets = []
    for key, value in fields.items():
        if key == "settings":
            sets.append("settings = settings || cast(:settings as jsonb)")   # merge, keep keys not sent
            params["settings"] = orjson.dumps(value).decode()
        else:
            sets.append(f"{key} = :{key}")
            params[key] = value.upper() if key == "state" and value else value
    return await db.one(f"update tenants set {', '.join(sets)} where id = :t returning *", params)


@router.post("/workspace/onboarding-step")
async def onboarding_step(step: int = Query(ge=1, le=8), db: TenantDb = Depends(tenant_db)):
    """The admin moved through the setup checklist. Step 8 = live."""
    db.ctx.require("tenant_admin")
    return await db.one(
        """update tenants set onboarding_step = greatest(onboarding_step, :s),
                  status = case when :s = 8 and status = 'onboarding' then 'active' else status end,
                  live_on = case when :s = 8 then coalesce(live_on, current_date) else live_on end
            where id = :t returning id, onboarding_step, status, live_on""",
        {"s": step, "t": db.ctx.tenant_id})

