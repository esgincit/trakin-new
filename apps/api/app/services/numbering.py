"""Document numbers from per-tenant templates kept in tenants.settings.numbering (PLAN WF-08).

Placeholders: {YEAR} {YY} {MM} {YYYYMM} {SEQ} {SEQ:n} (zero-padded to n) plus any the caller passes,
e.g. {CLIENT} {PROJECT}. A new entity type is a new key; its counter is mytrakin.next_number(tenant, key)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import orjson

DEFAULTS = {   # today's formats, so nothing changes until an admin edits them
    "project": "PRJ-{SEQ:2}",
    "msa": "MSA-{CLIENT}-{SEQ:3}", "subcontract": "SUB-{CLIENT}-{SEQ:3}", "ica": "ICA-{CLIENT}-{SEQ:3}",
    "nda": "NDA-{CLIENT}-{SEQ:3}", "offer_letter": "OFFER-{CLIENT}-{SEQ:3}",
    "sow": "SOW-{PROJECT}-{SEQ:3}", "contract": "CON-{YEAR}-{SEQ:4}",
    "invoice_ar": "AR-{YEAR}-{SEQ:4}", "invoice_ap": "AP-{YEAR}-{SEQ:4}", "envelope": "ENV-{SEQ:5}",
}
PLACEHOLDERS = ("CLIENT", "PROJECT")
COUNTER_KEYS = {"invoice_ar": "inv_AR", "invoice_ap": "inv_AP"}   # existing counters, so numbers don't restart
# Where each entity's numbers live, to skip numbers already taken (imports, hand-typed codes). Fixed, never user input.
_TAKEN = {"project": ("projects", "code"), "sow": ("sows", "code"), "contract": ("sows", "code"),
          "invoice_ar": ("invoices", "number"), "invoice_ap": ("invoices", "number"), "envelope": ("envelopes", "number"),
          **{k: ("agreements", "code") for k in ("msa", "subcontract", "ica", "nda", "offer_letter")}}
# ponytail: codes only collide with numbers already in use (imports, hand-typed); 50 skips is plenty.
MAX_TRIES = 50
_TOKEN = re.compile(r"\{([A-Z]+)(?::(\d+))?\}")


def format_code(template: str, seq: int, today: date, values: dict[str, Any]) -> str:
    def sub(m: re.Match) -> str:
        name, width = m.group(1), m.group(2)
        builtin = {"YEAR": f"{today:%Y}", "YY": f"{today:%y}", "MM": f"{today:%m}", "YYYYMM": f"{today:%Y%m}",
                   "SEQ": str(seq).zfill(int(width or 0))}
        if name in builtin:
            return builtin[name]
        if name in values:
            return re.sub(r"[^A-Z0-9]+", "", str(values[name] or "GEN").upper())[:12] or "GEN"
        raise ValueError(f"Unknown placeholder {{{name}}}")
    return _TOKEN.sub(sub, template)


def validate(templates: Any) -> dict[str, str]:
    """Templates an admin saves: a dict of entity → template with a {SEQ} and only known placeholders."""
    if not isinstance(templates, dict):
        raise ValueError("Numbering must be an object of entity → template")
    for entity, template in templates.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", str(entity)) or not isinstance(template, str) or len(template) > 60:
            raise ValueError(f"Bad numbering entry for '{entity}'")
        if "{SEQ" not in template:
            raise ValueError(f"The {entity} template needs {{SEQ}} so numbers stay unique")
        format_code(template, 1, date.today(), dict.fromkeys(PLACEHOLDERS, "X"))
    return templates


async def template_for(db, entity: str) -> str:
    saved = await db.val("select settings -> 'numbering' from tenants where id = :t", {"t": db.ctx.tenant_id})
    if isinstance(saved, (str, bytes)):
        saved = orjson.loads(saved)
    return (saved or {}).get(entity) or DEFAULTS[entity]


async def _taken(db, entity: str, code: str) -> bool:
    if entity not in _TAKEN:
        return False
    table, column = _TAKEN[entity]
    return bool(await db.val(f"select exists (select 1 from {table} where {column} = :c)", {"c": code}))


def counter_key(entity: str, template: str, values: dict[str, Any]) -> str:
    """One running number per entity; per client / per project when the template names them
    (SOW-{PROJECT}-{SEQ} → SOW-PRJ06-001, SOW-PRJ06-002 …; a new project starts at 001)."""
    if not re.search(r"\{(CLIENT|PROJECT)\}", template):
        return COUNTER_KEYS.get(entity, entity)
    scope = format_code(_TOKEN.sub(lambda m: m.group(0) if m.group(1) in PLACEHOLDERS else "", template), 0, date.today(), values)
    return f"{entity}:{scope}"


async def next_code(db, entity: str, **values: Any) -> str:
    """Take the next number for the entity (skipping any already in use)."""
    template = await template_for(db, entity)
    key = counter_key(entity, template, values)
    for _ in range(MAX_TRIES):
        seq = await db.val("select mytrakin.next_number(:t, :k)", {"t": db.ctx.tenant_id, "k": key})
        code = format_code(template, seq, date.today(), values)
        if not await _taken(db, entity, code):
            return code
    raise ValueError(f"Could not find a free {entity} number — check the numbering template")


async def preview_code(db, entity: str, **values: Any) -> str:
    """What next_code would give, without using up a number (for forms)."""
    template = await template_for(db, entity)
    seq = await db.val("select coalesce((select value from counters where key = :k), 0)",
                       {"k": counter_key(entity, template, values)})
    for step in range(1, MAX_TRIES + 1):
        code = format_code(template, seq + step, date.today(), values)
        if not await _taken(db, entity, code):
            return code
    return format_code(template, seq + 1, date.today(), values)
