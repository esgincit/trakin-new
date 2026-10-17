"""Acceptance of NDAs, MSAs, SOWs / work orders and amendments (PLAN WF-05, WF-06).

E-signature completion records acceptance automatically (public.py). This router records acceptance given outside
myTrakIn (signed on paper, accepted by e-mail) and returns the history for any record."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..deps import TenantDb, tenant_db
from ..errors import forbidden, not_found

router = APIRouter(tags=["acceptances"])

_TABLE = {"agreement": "agreements", "sow": "sows", "amendment": "sow_amendments"}   # fixed, never user input


class AcceptanceIn(BaseModel):
    entity_type: Literal["agreement", "sow", "amendment"]
    entity_id: UUID
    accepted_by: str = Field(min_length=2, max_length=200)   # who accepted, e.g. "J. Brooks (Atlas Foods)"
    note: str | None = Field(None, max_length=500)


@router.get("/acceptances")
async def acceptance_history(entity_type: Literal["agreement", "sow", "amendment"], entity_id: UUID,
                             db: TenantDb = Depends(tenant_db)):
    if not db.ctx.internal:
        raise forbidden()
    return await db.all(
        """select a.*, p.full_name as recorded_by from acceptances a left join profiles p on p.id = a.created_by
            where a.entity_type = :t and a.entity_id = :id order by a.accepted_at desc""",
        {"t": entity_type, "id": entity_id})


@router.post("/acceptances", status_code=201)
async def record_acceptance(body: AcceptanceIn, db: TenantDb = Depends(tenant_db)):
    """Record acceptance given outside myTrakIn. The agreement / SOW becomes active; an amendment is applied."""
    db.ctx.require("legal", "account_manager")
    table = _TABLE[body.entity_type]
    if not await db.val(f"select exists (select 1 from {table} where id = :id)", {"id": body.entity_id}):
        raise not_found(body.entity_type.capitalize())
    if body.entity_type == "amendment":
        await db.run("update sow_amendments set status = 'signed' where id = :id", {"id": body.entity_id})
        await db.run(
            """update sows s set end_date = coalesce(a.new_end_date, s.end_date),
                      value_cap = case when a.value_change is null then s.value_cap else coalesce(s.value_cap, 0) + a.value_change end
                 from sow_amendments a where a.id = :id and s.id = a.sow_id""", {"id": body.entity_id})
    elif body.entity_type == "agreement":
        # Paper acceptance of a company MSA is the counterparty accepting it; other agreements become active.
        await db.run("""update agreements
                           set status = case when kind in ('msa', 'subcontract') and company_id is not null
                                             then 'accepted' else 'active' end
                         where id = :id and status not in ('active', 'accepted')""", {"id": body.entity_id})
    else:
        await db.run(f"update {table} set status = 'active' where id = :id and status <> 'active'", {"id": body.entity_id})
    return await db.one(
        """insert into acceptances (tenant_id, entity_type, entity_id, accepted_by, method, note, created_by)
           values (:t, :type, :id, :by, 'manual', :note, :u) returning *""",
        {"t": db.ctx.tenant_id, "type": body.entity_type, "id": body.entity_id, "by": body.accepted_by.strip(),
         "note": body.note, "u": db.ctx.user_id})
