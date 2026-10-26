"""Tenant workflow switches (owner e-mail 2026-10-15, PLAN WF-01).

Register → Verify → NDA → MSA → Project → SOW → Acceptance → Resource contract → Acceptance → Timesheet → Invoice →
Payment → Payment confirmation. Every gate on that path reads these switches; none is hard-coded."""

from __future__ import annotations

from datetime import date
from typing import Any

import orjson

from ..errors import ApiError

DEFAULTS = {"requireNDA": True, "requireMSA": True, "requireAcceptance": True, "requireContract": True}

# Agreements that let a company (or 1099 contractor) be invoiced and paid.
MASTER_KINDS = ("msa", "subcontract", "ica")


def _as_dict(value: Any) -> dict:
    if isinstance(value, (str, bytes)):
        value = orjson.loads(value)
    return value or {}


async def rules(db) -> dict[str, bool]:
    saved = _as_dict(await db.val("select settings -> 'workflow' from tenants where id = :t", {"t": db.ctx.tenant_id}))
    return {k: bool(saved.get(k, v)) for k, v in DEFAULTS.items()}


def validate(switches: Any) -> dict[str, bool]:
    if not isinstance(switches, dict) or any(k not in DEFAULTS or not isinstance(v, bool) for k, v in switches.items()):
        raise ApiError(400, "bad_request", f"Workflow switches are {', '.join(DEFAULTS)} and must be true or false")
    return switches


async def pay_model(db, engagement: str) -> str:
    """payroll (W-2), vendor (C2C, E2E) or self (1099) — from the engagement_types table (WF-07)."""
    model = await db.val("select pay_model from engagement_types where code = :c and is_active", {"c": engagement})
    if model is None:
        raise ApiError(400, "bad_request", f"Unknown engagement type '{engagement}'")
    return model


def blocked(code: str, message: str) -> ApiError:
    """409 with a code the UI maps to the switch (Settings → Workflow) that would allow the action."""
    return ApiError(409, code, message)


async def has_active_agreement(db, *, kinds: tuple[str, ...], company_id: Any = None, consultant_id: Any = None,
                               on: date | None = None) -> bool:
    """An agreement in force (accepted, or active) of one of these kinds with the party covers the date.
    Pending and rejected MSAs don't count: the other company hasn't accepted them.
    An MSA lives in the workspace that sent it, so one the other company sent us counts too (shared_agreements).
    Matched by the company id first; a same-name company (how the counterparty was recorded here vs their own
    account) also matches — strictly a fallback under the exact branches, never a replacement for them."""
    return bool(await db.val(
        """select exists (select 1 from agreements
                           where status in ('active', 'accepted') and kind = any(:kinds)
                             and (company_id = cast(:co as uuid) or consultant_id = cast(:con as uuid))
                             and coalesce(effective_on, cast(:d as date)) <= :d
                             and coalesce(expires_on, cast(:d as date)) >= :d)
               or (cast(:co as uuid) is not null and exists (
                     select 1 from mytrakin.shared_agreements() s
                      where s.status in ('active', 'accepted') and s.kind = any(:kinds)
                        and mytrakin.agreement_peer_company(s.id) = cast(:co as uuid)
                        and coalesce(s.effective_on, cast(:d as date)) <= :d
                        and coalesce(s.expires_on, cast(:d as date)) >= :d))
               or (cast(:co as uuid) is not null and exists (
                     select 1 from companies me
                      join companies oc on lower(oc.name) = lower(me.name)
                     join agreements a2 on a2.company_id = oc.id
                                       and a2.tenant_id = mytrakin.ctx_tenant()
                                       and a2.status in ('active', 'accepted') and a2.kind = any(:kinds)
                                       and coalesce(a2.effective_on, cast(:d as date)) <= :d
                                       and coalesce(a2.expires_on, cast(:d as date)) >= :d
                      where me.id = :co))
               or (cast(:co as uuid) is not null and exists (
                     select 1 from companies me
                     join mytrakin.shared_agreements() s
                       on lower(coalesce(s.counterparty, '')) = lower(me.name)
                      and s.status in ('active', 'accepted') and s.kind = any(:kinds)
                      and coalesce(s.effective_on, cast(:d as date)) <= :d
                      and coalesce(s.expires_on, cast(:d as date)) >= :d
                      where me.id = :co))""",
        {"kinds": list(kinds), "co": company_id, "con": consultant_id, "d": on or date.today()}))
