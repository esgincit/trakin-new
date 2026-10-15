"""Roles & permissions — only the company owner configures them.

A custom role is a base role (row scope + amount masking, unchanged) plus a module → none/read/write
map; a person can also get per-module exceptions. Enforcement lives in deps.tenant_db (permissions.check).
"""

from __future__ import annotations

from uuid import UUID

import orjson
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from ..deps import INTERNAL_ROLES, TenantDb, tenant_db
from ..errors import bad_request, conflict, forbidden, not_found
from ..permissions import LEVELS, MODULES

router = APIRouter(tags=["roles & permissions"])
BASE_ROLES = "^(tenant_admin|finance|account_manager|legal|hr|approver|viewer|vendor_admin|client_user|consultant)$"


def _owner(db: TenantDb) -> None:
    if not db.ctx.is_owner:
        raise forbidden("Only the company owner can change roles and permissions")


def _valid(perms: dict[str, str] | None) -> dict[str, str] | None:
    for k, v in (perms or {}).items():
        if k not in MODULES:
            raise ValueError(f"Unknown module '{k}'")
        if v not in LEVELS:
            raise ValueError(f"'{v}' must be one of none, read, write")
    return perms


class RoleIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    base_role: str = Field(pattern=BASE_ROLES)
    permissions: dict[str, str] = {}

    @field_validator("permissions")
    @classmethod
    def _p(cls, v):
        return _valid(v)


class RolePatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=60)
    permissions: dict[str, str] | None = None

    @field_validator("permissions")
    @classmethod
    def _p(cls, v):
        return _valid(v)


class AccessIn(BaseModel):
    custom_role_id: UUID | None = None
    permission_overrides: dict[str, str] | None = None

    @field_validator("permission_overrides")
    @classmethod
    def _p(cls, v):
        return _valid(v)


@router.get("/roles")
async def list_roles(db: TenantDb = Depends(tenant_db)):
    _owner(db)
    roles = await db.all("""select r.*, (select count(*) from memberships m where m.custom_role_id = r.id) as members
                              from custom_roles r order by r.name""")
    return {"modules": [{"key": k, "label": v[0]} for k, v in MODULES.items()], "levels": LEVELS, "roles": roles}


@router.post("/roles", status_code=201)
async def create_role(body: RoleIn, db: TenantDb = Depends(tenant_db)):
    _owner(db)
    if await db.val("select 1 from custom_roles where lower(name) = lower(:n)", {"n": body.name.strip()}):
        raise conflict("A role with this name already exists")
    return await db.one(
        """insert into custom_roles (tenant_id, name, base_role, permissions, created_by)
           values (:t, :n, :b, cast(:p as jsonb), :u) returning *""",
        {"t": db.ctx.tenant_id, "n": body.name.strip(), "b": body.base_role,
         "p": orjson.dumps(body.permissions).decode(), "u": db.ctx.user_id})


@router.patch("/roles/{role_id}")
async def update_role(role_id: UUID, body: RolePatch, db: TenantDb = Depends(tenant_db)):
    _owner(db)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise bad_request("Nothing to change")
    if fields.get("name"):
        fields["name"] = fields["name"].strip()
        if await db.val("select 1 from custom_roles where lower(name) = lower(:n) and id <> :id",
                        {"n": fields["name"], "id": role_id}):
            raise conflict("A role with this name already exists")
    if "permissions" in fields:
        fields["permissions"] = orjson.dumps(fields["permissions"] or {}).decode()
    sets = ", ".join(f"{k} = cast(:{k} as jsonb)" if k == "permissions" else f"{k} = :{k}" for k in fields)
    row = await db.one(f"update custom_roles set {sets} where id = :id returning *", {**fields, "id": role_id})
    if row is None:
        raise not_found("Role")
    return row


@router.delete("/roles/{role_id}")
async def delete_role(role_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Members of a deleted role fall back to their base role's access."""
    _owner(db)
    if await db.run("delete from custom_roles where id = :id", {"id": role_id}) == 0:
        raise not_found("Role")
    return {"id": role_id, "deleted": True}


@router.patch("/users/{membership_id}/access")
async def set_access(membership_id: UUID, body: AccessIn, db: TenantDb = Depends(tenant_db)):
    """Give someone a custom role and/or per-module exceptions. A custom role also sets their base role."""
    _owner(db)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise bad_request("Nothing to change")
    if membership_id == db.ctx.membership_id:
        raise bad_request("The owner always has full access")
    sets, params = [], {"id": membership_id}
    if "custom_role_id" in fields:
        sets.append("custom_role_id = :rid")
        params["rid"] = fields["custom_role_id"]
        if fields["custom_role_id"] is not None:
            base = await db.val("select base_role from custom_roles where id = :r", {"r": fields["custom_role_id"]})
            if base is None:
                raise not_found("Role")
            current = await db.val("select role from memberships where id = :id", {"id": membership_id})
            if current is None:
                raise not_found("User")
            if base != current and not (base in INTERNAL_ROLES and current in INTERNAL_ROLES):
                # vendor / client / consultant logins are tied to their company or consultant record
                raise bad_request(f"This role is based on {base.replace('_', ' ')} and can't be given to a "
                                  f"{current.replace('_', ' ')} login")
            sets.append("role = :base")
            params["base"] = base
    if "permission_overrides" in fields:
        sets.append("permission_overrides = cast(:ov as jsonb)")
        params["ov"] = orjson.dumps(fields["permission_overrides"] or {}).decode()
    row = await db.one(f"update memberships set {', '.join(sets)} where id = :id "
                       "returning id, role, custom_role_id, permission_overrides", params)
    if row is None:
        raise not_found("User")
    return row
