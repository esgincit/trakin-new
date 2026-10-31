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
    """payroll (W-2), vendor (C2C, E2E) or self (1099) - from the engagement_types table (WF-07)."""
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
    Matched by the company id first; a same-name company also matches — the counterparty can be recorded
    here as a local company while the project / SOW names its own directory record (or the other way round)
    — as a fallback under the exact branches, never a replacement for them.
    An agreement sent for e-signature ('out_for_signature') is treated as in force once the envelope
    has been completed, since the other party has signed it."""
    return bool(await db.val(
        """select exists (select 1 from agreements
                           where status in ('active', 'accepted', 'out_for_signature') and kind = any(:kinds)
                             and (company_id = cast(:co as uuid) or consultant_id = cast(:con as uuid))
                             and coalesce(effective_on, cast(:d as date)) <= :d
                             and coalesce(expires_on, cast(:d as date)) >= :d)
              or (cast(:co as uuid) is not null and exists (
                    select 1 from mytrakin.shared_agreements() s
                     where s.status in ('active', 'accepted', 'out_for_signature') and s.kind = any(:kinds)
                       and mytrakin.agreement_peer_company(s.id) = cast(:co as uuid)
                       and coalesce(s.effective_on, cast(:d as date)) <= :d
                       and coalesce(s.expires_on, cast(:d as date)) >= :d))
              or (cast(:co as uuid) is not null and exists (
                    select 1 from companies me
                     join companies oc on lower(regexp_replace(oc.name, '[^a-zA-Z0-9]', '', 'g')) =
                                        lower(regexp_replace(me.name, '[^a-zA-Z0-9]', '', 'g'))
                     join agreements a2 on a2.company_id = oc.id
                                       and a2.tenant_id = mytrakin.ctx_tenant()
                                       and a2.status in ('active', 'accepted', 'out_for_signature') and a2.kind = any(:kinds)
                                       and coalesce(a2.effective_on, cast(:d as date)) <= :d
                                       and coalesce(a2.expires_on, cast(:d as date)) >= :d
                       where me.id = :co))
              or (cast(:co as uuid) is not null and exists (
                    select 1 from companies me
                    join mytrakin.shared_agreements() s
                      on lower(regexp_replace(coalesce(s.counterparty, ''), '[^a-zA-Z0-9]', '', 'g')) =
                                         lower(regexp_replace(me.name, '[^a-zA-Z0-9]', '', 'g'))
                     and s.status in ('active', 'accepted', 'out_for_signature') and s.kind = any(:kinds)
                     and coalesce(s.effective_on, cast(:d as date)) <= :d
                     and coalesce(s.expires_on, cast(:d as date)) >= :d
                     where me.id = :co))
              -- A project / SOW can name the counterparty by its own directory record while the
              -- agreements were recorded against a local company with the same name (or the
              -- other way round). Match those by name as well; the company-id branches above
              -- always win, this is only a fallback under them.
              or (cast(:co as uuid) is not null and exists (
                    select 1 from agreements a3
                     where a3.tenant_id = mytrakin.ctx_tenant()
                       and a3.status in ('active', 'accepted', 'out_for_signature') and a3.kind = any(:kinds)
                       and coalesce(a3.effective_on, cast(:d as date)) <= :d
                       and coalesce(a3.expires_on, cast(:d as date)) >= :d
                       and length(regexp_replace(coalesce(mytrakin.company_public_name(cast(:co as uuid)), ''),
                                                 '[^a-zA-Z0-9]', '', 'g')) > 0
                       and lower(regexp_replace(coalesce(mytrakin.company_public_name(a3.company_id), ''),
                                                '[^a-zA-Z0-9]', '', 'g')) =
                           lower(regexp_replace(coalesce(mytrakin.company_public_name(cast(:co as uuid)), ''),
                                                '[^a-zA-Z0-9]', '', 'g'))))
              or (cast(:co as uuid) is not null and exists (
                    select 1 from mytrakin.shared_agreements() s
                     where s.status in ('active', 'accepted', 'out_for_signature') and s.kind = any(:kinds)
                       and coalesce(s.effective_on, cast(:d as date)) <= :d
                       and coalesce(s.expires_on, cast(:d as date)) >= :d
                       and length(regexp_replace(coalesce(mytrakin.company_public_name(cast(:co as uuid)), ''),
                                                 '[^a-zA-Z0-9]', '', 'g')) > 0
                       and lower(regexp_replace(coalesce(s.counterparty, ''), '[^a-zA-Z0-9]', '', 'g')) =
                           lower(regexp_replace(coalesce(mytrakin.company_public_name(cast(:co as uuid)), ''),
                                                '[^a-zA-Z0-9]', '', 'g'))))""",
        {"kinds": list(kinds), "co": company_id, "con": consultant_id, "d": on or date.today()}))


async def stale_note(db, *, kinds: tuple[str, ...], company_id: Any = None) -> str | None:
    """Why no agreement of these kinds is in force with the party, as one human clause (or None).

    The screen may still show the agreement as Active — the status field is only switched at
    renewal/termination, never when the end date passes — so a plain 'no signed NDA' reads as a
    contradiction. Point at the closest agreement and its dates instead: 'NDA TGS-001 expired on
    16 Oct 2026' or 'MSA MSA-EX-001 is still pending the other company's signature'."""
    if not company_id:
        return None
    row = await db.one(
        """select code, kind, status, effective_on, expires_on
             from (select a.code, a.kind, a.status, a.effective_on, a.expires_on
                     from agreements a
                    where a.kind = any(:kinds)
                      and a.status not in ('draft', 'rejected')
                      and (a.company_id = cast(:co as uuid)
                           or (length(regexp_replace(
                                 coalesce(mytrakin.company_public_name(cast(:co as uuid)), ''),
                                 '[^a-zA-Z0-9]', '', 'g')) > 0
                               and lower(regexp_replace(
                                     coalesce(mytrakin.company_public_name(a.company_id), ''),
                                     '[^a-zA-Z0-9]', '', 'g')) =
                                   lower(regexp_replace(
                                     coalesce(mytrakin.company_public_name(cast(:co as uuid)), ''),
                                     '[^a-zA-Z0-9]', '', 'g'))))
                    union all
                   select s.code, s.kind, s.status, s.effective_on, s.expires_on
                     from mytrakin.shared_agreements() s
                    where s.kind = any(:kinds)
                      and s.status not in ('draft', 'rejected')
                      and (mytrakin.agreement_peer_company(s.id) = cast(:co as uuid)
                           or (length(regexp_replace(
                                 coalesce(mytrakin.company_public_name(cast(:co as uuid)), ''),
                                 '[^a-zA-Z0-9]', '', 'g')) > 0
                               and lower(regexp_replace(coalesce(s.counterparty, ''), '[^a-zA-Z0-9]', '', 'g')) =
                                   lower(regexp_replace(
                                     coalesce(mytrakin.company_public_name(cast(:co as uuid)), ''),
                                     '[^a-zA-Z0-9]', '', 'g'))))) t
            order by (status in ('active', 'accepted', 'out_for_signature')) desc, expires_on desc nulls last
            limit 1""",
        {"kinds": list(kinds), "co": company_id})
    if row is None:
        return None
    lbl = {"nda": "NDA", "msa": "MSA", "subcontract": "subcontract", "ica": "contractor agreement"}
    lbl = lbl.get(row["kind"], row["kind"])
    today = date.today()
    if row["status"] == "pending":
        return f"{lbl} {row['code']} is still pending — the other company has to sign or accept it"
    if row["status"] == "out_for_signature":
        return f"{lbl} {row['code']} is out for signature"
    if row["expires_on"] and row["expires_on"] < today:
        return f"{lbl} {row['code']} expired on {row['expires_on'].day} {row['expires_on']:%b %Y} — renew or replace it"
    if row["effective_on"] and row["effective_on"] > today:
        return f"{lbl} {row['code']} only starts on {row['effective_on'].day} {row['effective_on']:%b %Y}"
    return None
