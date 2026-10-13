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

from .config import get_settings
from .db import Db, get_engine
from .errors import ApiError, forbidden
from .security import Claims, bearer_token, decode_token
from .utils import client_ip, user_agent

INTERNAL_ROLES = {"tenant_admin", "finance", "account_manager", "legal", "hr", "approver", "viewer", "system"}
MONEY_ROLES = {"tenant_admin", "finance"}


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


async def tenant_db(request: Request, claims: Claims = Depends(current_claims)) -> AsyncIterator[TenantDb]:
    ip, ua = client_ip(request), user_agent(request)
    async with get_engine().begin() as conn:
        row = (await conn.execute(text(_START_SQL), {"uid": claims.user_id, "tid": _tenant_header(request),
                                                     "ip": ip, "ua": ua})).mappings().first()
        if row is None:
            raise ApiError(403, "no_access", "You don't have access to this workspace yet. Ask your administrator for an invite.")
        ctx = Ctx(user_id=claims.user_id, tenant_id=row["tenant_id"], role=row["role"], email=claims.email,
                  company_id=row["company_id"], consultant_id=row["consultant_id"],
                  membership_id=row["membership_id"], is_platform_admin=row["is_platform_admin"], ip=ip, user_agent=ua)
        if get_settings().require_mfa_for_money_roles and ctx.role in MONEY_ROLES and claims.aal != "aal2":
            raise ApiError(403, "mfa_required", "Finish two-step verification to use money features.")
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
            raise forbidden("Only the platform owner can open the platform console")
        await conn.execute(text("select mytrakin.begin_request(:uid, null, 'platform_admin', null, null, :ip, :ua)"),
                           {"uid": claims.user_id, "ip": ip, "ua": ua})
        yield TenantDb(conn, Ctx(user_id=claims.user_id, tenant_id=None, role="platform_admin", email=claims.email,
                                 is_platform_admin=True, ip=ip, user_agent=ua))


async def user_db(request: Request, claims: Claims = Depends(current_claims)) -> AsyncIterator[TenantDb]:
    """Signed-in user without a tenant role yet (e.g. reading their own profile / tenant list)."""
    ip, ua = client_ip(request), user_agent(request)
    async with get_engine().begin() as conn:
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


async def open_system(tenant_id: UUID) -> AsyncIterator[TenantDb]:
    async with get_engine().begin() as conn:
        await conn.execute(text("select mytrakin.begin_request(null, :tid, 'system')"), {"tid": tenant_id})
        yield TenantDb(conn, Ctx(user_id=None, tenant_id=tenant_id, role="system"))
