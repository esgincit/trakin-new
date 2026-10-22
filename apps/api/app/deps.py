"""Request context and FastAPI dependencies.

    tenant_db    signed-in user acting inside one tenant (header X-Tenant-Id picks which)
    platform_db  platform owner console (no tenant)
    public_db    anonymous visitors (registration forms)
    signer_db    someone following an e-signature link
    system_db    scheduled jobs, one tenant at a time
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import text

from . import permissions
from .db import Db, get_engine
from .errors import ApiError, forbidden
from .security import Claims, bearer_token, decode_token
from .utils import client_ip, user_agent

INTERNAL_ROLES = {"tenant_admin", "finance", "account_manager", "legal", "hr", "approver", "viewer", "system"}


@dataclass
class Ctx:
    user_id: UUID | None
    tenant_id: UUID | None
    role: str
    email: str | None = None
    company_id: UUID | None = None
    consultant_id: UUID | None = None
    membership_id: UUID | None = None
    signer_id: UUID | None = None
    is_platform_admin: bool = False
    is_owner: bool = False
    permissions: dict = field(default_factory=dict)
    ip: str | None = None
    user_agent: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def internal(self) -> bool:
        return self.role in INTERNAL_ROLES

    def allows(self, *roles: str) -> bool:
        return self.role in roles or self.role in {"tenant_admin", "system"}

    def require(self, *roles: str) -> None:
        if not self.allows(*roles):
            raise forbidden()

    # What money a role may see (row access is enforced by RLS; this hides columns).
    @property
    def sees_bill_rate(self) -> bool:
        return self.role in {"tenant_admin", "finance", "legal", "account_manager", "system", "client_user"}

    @property
    def sees_pay_rate(self) -> bool:
        return self.role in {"tenant_admin", "finance", "legal", "system", "vendor_admin"}


class TenantDb(Db):
    def __init__(self, conn, ctx: Ctx):
        super().__init__(conn)
        self.ctx = ctx


async def current_claims(request: Request) -> Claims:
    claims = decode_token(bearer_token(request))
    request.state.claims = claims
    return claims


def _tenant_header(request: Request) -> UUID | None:
    raw = request.headers.get("x-tenant-id")
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError as exc:
        raise ApiError(400, "invalid", "X-Tenant-Id must be a UUID") from exc


_START_SQL = """
select a.tenant_id, a.role, a.company_id, a.consultant_id, a.membership_id, a.is_platform_admin,
       mytrakin.begin_request(:uid, a.tenant_id, a.role, a.company_id, a.consultant_id, :ip, :ua)
  from mytrakin.resolve_access(:uid, :tid) a
"""


_COMPANY_TENANT_SQL = """
select cm.tenant_id, 'member' as role, null::uuid as company_id, null::uuid as consultant_id,
       null::uuid as membership_id, false as is_platform_admin,
       mytrakin.begin_request(:uid, cm.tenant_id, 'member', null, null, :ip, :ua)
  from mytrakin.company_members cm
  join mytrakin.tenants t on t.id = cm.tenant_id
 where cm.user_id = :uid and cm.status = 'active' and t.status <> 'closed'
   and (cast(:tid as uuid) is null or cm.tenant_id = :tid)
 order by cm.created_at
 limit 1
"""


# Paths a company may use while it waits for platform activation.
PENDING_OK = ("/v1/session", "/v1/companies", "/v1/onboarding")


async def _account_state(conn, ctx: Ctx):
    """Company status, whether the caller owns it, and their custom role / exceptions (one round trip)."""
    return (await conn.execute(text(
        """select t.status, t.owner_membership_id = cast(:m as uuid) as is_owner,
                  m.permission_overrides, r.permissions as role_permissions, r.name as custom_role
             from mytrakin.tenants t
             left join mytrakin.memberships m on m.id = cast(:m as uuid)
             left join mytrakin.custom_roles r on r.id = m.custom_role_id
            where t.id = :t"""), {"t": ctx.tenant_id, "m": ctx.membership_id})).mappings().first()


async def _second_step(conn, claims: Claims) -> None:
    """Two-step verification is the user's choice; once they turn it on, every session must finish it."""
    if claims.aal != "aal2" and (await conn.execute(text("select mytrakin.user_has_mfa(:u)"),
                                                     {"u": claims.user_id})).scalar():
        raise ApiError(403, "mfa_required", "You turned on two-step verification — enter your code to continue.")


def _gate(request: Request, state) -> None:
    if state["status"] == "onboarding" and not request.url.path.startswith(PENDING_OK):
        raise ApiError(403, "pending_activation",
                       "Your company is waiting for activation by the myTrakIn team. "
                       "You can finish your company profile meanwhile.")


async def tenant_db(request: Request, claims: Claims = Depends(current_claims)) -> AsyncIterator[TenantDb]:
    ip, ua = client_ip(request), user_agent(request)
    async with get_engine().begin() as conn:
        params = {"uid": claims.user_id, "tid": _tenant_header(request), "ip": ip, "ua": ua}
        row = (await conn.execute(text(_START_SQL), params)).mappings().first()
        if row is None:
            # No workspace membership — but an active company membership still grants
            # role 'member' inside that company's workspace (company profiles, members,
            # onboarding). Everything else stays role-gated downstream.
            row = (await conn.execute(text(_COMPANY_TENANT_SQL), params)).mappings().first()
        if row is None:
            raise ApiError(403, "no_access", "You don't have access to this company yet. Ask its owner for an invite.")
        ctx = Ctx(user_id=claims.user_id, tenant_id=row["tenant_id"], role=row["role"], email=claims.email,
                  company_id=row["company_id"], consultant_id=row["consultant_id"],
                  membership_id=row["membership_id"], is_platform_admin=row["is_platform_admin"], ip=ip, user_agent=ua)
        await _second_step(conn, claims)
        state = await _account_state(conn, ctx)
        ctx.is_owner = bool(state["is_owner"])
        _gate(request, state)
        ctx.permissions = permissions.effective(state["role_permissions"], state["permission_overrides"])
        ctx.extra["custom_role"] = state["custom_role"]
        permissions.check(ctx.permissions, request.method, request.url.path, is_owner=ctx.is_owner)
        if ctx.membership_id is not None:
            # "Last active" for the users list and the owner console; written at most every 5 minutes.
            await conn.execute(text("""update mytrakin.memberships set last_active_at = now()
                                        where id = :id and (last_active_at is null or last_active_at < now() - interval '5 minutes')"""),
                               {"id": ctx.membership_id})
        yield TenantDb(conn, ctx)


async def member_db(request: Request, claims: Claims = Depends(current_claims)) -> AsyncIterator[TenantDb]:
    """For pages that belong to the person, not a workspace (the network). Inside a workspace this is `tenant_db`;
    someone who hasn't been invited anywhere yet simply acts as themselves, so a new Google/Microsoft sign-up
    can use the feed, people and messages straight away."""
    ip, ua = client_ip(request), user_agent(request)
    async with get_engine().begin() as conn:
        await _second_step(conn, claims)
        row = (await conn.execute(text(_START_SQL), {"uid": claims.user_id, "tid": _tenant_header(request),
                                                     "ip": ip, "ua": ua})).mappings().first()
        if row is None:
            await conn.execute(text("select mytrakin.begin_request(:uid, null, 'member', null, null, :ip, :ua)"),
                               {"uid": claims.user_id, "ip": ip, "ua": ua})
            yield TenantDb(conn, Ctx(user_id=claims.user_id, tenant_id=None, role="member", email=claims.email, ip=ip, user_agent=ua))
            return
        ctx = Ctx(user_id=claims.user_id, tenant_id=row["tenant_id"], role=row["role"], email=claims.email,
                  company_id=row["company_id"], consultant_id=row["consultant_id"],
                  membership_id=row["membership_id"], is_platform_admin=row["is_platform_admin"], ip=ip, user_agent=ua)
        yield TenantDb(conn, ctx)


async def onboarding_db(request: Request, claims: Claims = Depends(current_claims)) -> AsyncIterator[TenantDb]:
    """Company creation: workspace members act with their own role; people whose only
    tie is a company membership (freelancers, client/vendor contacts) act as 'member'
    inside that company's workspace. Money movement stays staff-gated downstream."""
    ip, ua = client_ip(request), user_agent(request)
    async with get_engine().begin() as conn:
        await _second_step(conn, claims)
        params = {"uid": claims.user_id, "tid": _tenant_header(request), "ip": ip, "ua": ua}
        row = (await conn.execute(text(_START_SQL), params)).mappings().first()
        if row is None:
            row = (await conn.execute(text(_COMPANY_TENANT_SQL), params)).mappings().first()
        if row is None:
            raise ApiError(403, "no_access", "You don't have access to this company yet. Ask its owner for an invite.")
        ctx = Ctx(user_id=claims.user_id, tenant_id=row["tenant_id"], role=row["role"], email=claims.email,
                  company_id=row["company_id"], consultant_id=row["consultant_id"],
                  membership_id=row["membership_id"], is_platform_admin=row["is_platform_admin"], ip=ip, user_agent=ua)
        if ctx.membership_id is not None:
            # "Last active" for the users list and the owner console; written at most every 5 minutes.
            await conn.execute(text("""update mytrakin.memberships set last_active_at = now()
                                        where id = :id and (last_active_at is null or last_active_at < now() - interval '5 minutes')"""),
                               {"id": ctx.membership_id})
        yield TenantDb(conn, ctx)


async def platform_db(request: Request, claims: Claims = Depends(current_claims)) -> AsyncIterator[TenantDb]:
    ip, ua = client_ip(request), user_agent(request)
    async with get_engine().begin() as conn:
        is_admin = (await conn.execute(text("select mytrakin.is_platform_admin_user(:uid)"), {"uid": claims.user_id})).scalar()
        if not is_admin:
            raise forbidden("Only a platform admin can open the platform console")
        await _second_step(conn, claims)
        await conn.execute(text("select mytrakin.begin_request(:uid, null, 'platform_admin', null, null, :ip, :ua)"),
                           {"uid": claims.user_id, "ip": ip, "ua": ua})
        yield TenantDb(conn, Ctx(user_id=claims.user_id, tenant_id=None, role="platform_admin", email=claims.email,
                                 is_platform_admin=True, ip=ip, user_agent=ua))


async def user_db(request: Request, claims: Claims = Depends(current_claims)) -> AsyncIterator[TenantDb]:
    """Signed-in user without a tenant role yet (e.g. reading their own profile / tenant list)."""
    ip, ua = client_ip(request), user_agent(request)
    async with get_engine().begin() as conn:
        await _second_step(conn, claims)
        await conn.execute(text("select mytrakin.begin_request(:uid, null, 'member', null, null, :ip, :ua)"),
                           {"uid": claims.user_id, "ip": ip, "ua": ua})
        yield TenantDb(conn, Ctx(user_id=claims.user_id, tenant_id=None, role="member", email=claims.email, ip=ip, user_agent=ua))


async def open_public(request: Request, tenant_id: UUID | None) -> AsyncIterator[TenantDb]:
    ip, ua = client_ip(request), user_agent(request)
    async with get_engine().begin() as conn:
        await conn.execute(text("select mytrakin.begin_request(null, :tid, 'public', null, null, :ip, :ua)"),
                           {"tid": tenant_id, "ip": ip, "ua": ua})
        yield TenantDb(conn, Ctx(user_id=None, tenant_id=tenant_id, role="public", ip=ip, user_agent=ua))


async def open_signer(request: Request, token_hash: str) -> AsyncIterator[TenantDb]:
    ip, ua = client_ip(request), user_agent(request)
    async with get_engine().begin() as conn:
        found = (await conn.execute(text("select * from mytrakin.esign_lookup(:h)"), {"h": token_hash})).mappings().first()
        if found is None:
            raise ApiError(404, "link_invalid", "This signing link is not valid. Ask the sender for a new one.")
        await conn.execute(
            text("select mytrakin.begin_request(null, :tid, 'signer', null, null, :ip, :ua, :sid)"),
            {"tid": found["tenant_id"], "ip": ip, "ua": ua, "sid": found["signer_id"]},
        )
        yield TenantDb(conn, Ctx(user_id=None, tenant_id=found["tenant_id"], role="signer",
                                 signer_id=found["signer_id"], ip=ip, user_agent=ua,
                                 extra={"envelope_id": found["envelope_id"]}))


async def open_ts_approver(request: Request, token_hash: str) -> AsyncIterator[TenantDb]:
    """A personal approval link for the end client's timesheet manager.
    Read/decides through ts_approval_view / ts_client_decide, not table RLS."""
    ip, ua = client_ip(request), user_agent(request)
    async with get_engine().begin() as conn:
        found = (await conn.execute(text(
            "select tenant_id, timesheet_id from mytrakin.ts_approval_links where token_hash = :h"),
            {"h": token_hash})).mappings().first()
        if found is None:
            raise ApiError(404, "link_invalid", "This approval link is not valid. Ask the placing company for a new one.")
        await conn.execute(
            text("select mytrakin.begin_request(null, :tid, 'signer', null, null, :ip, :ua)"),
            {"tid": found["tenant_id"], "ip": ip, "ua": ua},
        )
        yield TenantDb(conn, Ctx(user_id=None, tenant_id=found["tenant_id"], role="signer", ip=ip, user_agent=ua,
                                 extra={"timesheet_id": found["timesheet_id"]}))


async def open_system(tenant_id: UUID) -> AsyncIterator[TenantDb]:
    async with get_engine().begin() as conn:
        await conn.execute(text("select mytrakin.begin_request(null, :tid, 'system')"), {"tid": tenant_id})
        yield TenantDb(conn, Ctx(user_id=None, tenant_id=tenant_id, role="system"))
