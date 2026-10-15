# Phase W — Approved workflow (owner e-mail master spec) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register → Verify → NDA → MSA → Project → SOW → Acceptance → Resource contract → Acceptance → Timesheet →
Invoice → Payment → Payment confirmation works end to end, with every gate switchable per tenant (PLAN §5.30 WF-01…11).
Internal release **2026-10-25**, go-live **2026-10-30**. Business logic first, minimal UI last.

**Source:** `docs/requirements/2026-10-15-mail-master-spec.md` (wins over the prototype — PLAN RULE-07 amended).
Owner answers: E2E = **employer-to-employer** (a vendor company employs the consultant; paperwork like C2C).

**Architecture — reuse, don't rebuild.** The e-mail's entity list maps onto tables that already exist; only the missing
pieces are added. Existing data and APIs keep working (new columns nullable or defaulted, old status values kept).

| E-mail entity | Existing table | Change |
|---|---|---|
| Project | `projects` | activation gate (W.5) |
| SOW | `sows` | **add `project_id`** (W.4) |
| SOWResource / ResourceAssignment | `placements` (`ar_sow_id` = client SOW, `ap_sow_id` = resource contract) | endpoints under `/sows/{id}/resources` |
| Contract (resource) | `sows` with `side='we_pay'` (vendor / 1099 work order) or `agreements.kind='offer_letter'` (W-2) | gate (W.6) |
| NDA, MSA | `agreements` (`kind` nda / msa / subcontract / ica) | gates (W.5) |
| Acceptance | — | **new `acceptances` table** (W.6) |
| Timesheet, Invoice | `timesheets`, `invoices` | gates only |
| Payment | `payments` | **add `status`, `confirmed_by`, `confirmed_at`** (W.7) |
| PaymentConfirmation | — | columns on `payments` + `POST /payments/{id}/confirm` |
| ContractType | `consultants.engagement` check constraint | **new `engagement_types` table** (W.2) |
| Tenant configuration | `tenants.settings` jsonb (merged by `PATCH /workspace`) | keys `workflow`, `numbering` (W.1, W.3) |
| Status / approval history | `audit_log` triggers on every table | add new tables to the audit trigger list |

Status names: the e-mail's "recommended" statuses are **labels** over existing values (no data rewrite): SOW
`draft`→Draft, `out_for_signature`→Pending acceptance, `active`→Accepted, `ended`/`terminated`→Closed; project
`planned`→Draft, `active`→Active, `completed`→Closed. Add to `apps/web/src/lib/format.ts` `label()`.

**Tech:** FastAPI raw SQL, Supabase Postgres + RLS, pytest in CI (no local Postgres here — push the branch, read
`gh run view <id> --log-failed`), Next.js 16.

## Ground rules
- `CLAUDE.md`, PLAN §0 DoD, RULE-01…06 (AR/AP only, role masking). New migration per change, never edit applied ones;
  every new tenant table: `tenant_id`, RLS policies, audit trigger, index on `tenant_id`.
- Tests: new file `apps/api/tests/test_workflow.py`; tests share the seeded DB and must restore anything they change.
- Switches default **on** (as the e-mail requires); the seed must satisfy them (seed has MSAs; W.5 adds seed NDAs) so
  existing tests stay green.
- Branch `feat/wf-workflow` off `main`. Commit per task; push only when the user agrees.

## Schedule
| Day | Tasks |
|---|---|
| 15–16 Oct | W.0 CI green · W.1 switches · W.8 money-safety |
| 17–18 Oct | W.2 engagement types · W.3 naming engine |
| 19–20 Oct | W.4 SOW→project + resources · W.5 NDA/MSA gates |
| 21–22 Oct | W.6 acceptance + contract gate · W.7 payment confirmation |
| 23–24 Oct | W.9 workflow tests · W.10 minimal UI · docs |
| 25 Oct | Internal release (deploy, smoke test per role) |

---

### W.0 — CI green
Task 0 of `2026-10-15-contracts-projects-timesheets-gaps.md`: `companies.py:440` count
`company_role in ('super_admin','owner')`; `onboarding.py:417` message "Upload the Memorandum of Association (MOA)
first"; test demotes the invited owner instead of the removed `owner` creator. Commit; CI green before W.1.

### W.1 — Workflow switches (WF-01)
**Files:** create `apps/api/app/services/workflow.py`; modify `apps/api/app/routers/admin.py`; test `test_workflow.py`.

- [ ] Test first:

```python
async def test_workflow_switches_default_on_and_admin_can_change(client, auth):
    ws = (await client.get("/workspace/workflow", headers=auth("finance"))).json()
    assert ws == {"requireNDA": True, "requireMSA": True, "requireAcceptance": True, "requireContract": True}
    off = await client.patch("/workspace", headers=auth("admin"), json={"settings": {"workflow": {"requireNDA": False}}})
    assert off.status_code == 200
    now = (await client.get("/workspace/workflow", headers=auth("finance"))).json()
    assert now["requireNDA"] is False and now["requireMSA"] is True      # other switches kept
    await client.patch("/workspace", headers=auth("admin"), json={"settings": {"workflow": {"requireNDA": True}}})
    bad = await client.patch("/workspace", headers=auth("admin"), json={"settings": {"workflow": {"requireXYZ": True}}})
    assert bad.status_code == 400
```
- [ ] `services/workflow.py`:

```python
"""Tenant workflow switches (owner e-mail 2026-10-15, WF-01). Every gate reads these; nothing is hard-coded."""

from __future__ import annotations

from typing import Any

from ..errors import ApiError

DEFAULTS = {"requireNDA": True, "requireMSA": True, "requireAcceptance": True, "requireContract": True}


async def rules(db) -> dict[str, bool]:
    saved = await db.val("select settings -> 'workflow' from tenants where id = :t", {"t": db.ctx.tenant_id}) or {}
    return {k: bool(saved.get(k, v)) for k, v in DEFAULTS.items()}


def blocked(code: str, message: str) -> ApiError:
    """409 with a code the UI can map to the switch that would allow the action."""
    return ApiError(409, code, message)


async def has_active_agreement(db, *, kinds: tuple[str, ...], company_id: Any = None, consultant_id: Any = None,
                               on) -> bool:
    return bool(await db.val(
        """select exists (select 1 from agreements
                           where status = 'active' and kind = any(:kinds)
                             and (company_id = cast(:co as uuid) or consultant_id = cast(:con as uuid))
                             and coalesce(effective_on, cast(:d as date)) <= :d
                             and coalesce(expires_on, cast(:d as date)) >= :d)""",
        {"kinds": list(kinds), "co": company_id, "con": consultant_id, "d": on}))
```
  (Check whether `db.val` returns jsonb as dict in `app/db.py`; if it returns str, `orjson.loads` it.)
- [ ] `admin.py`: `GET /workspace/workflow` (internal roles) → `await workflow.rules(db)`. In `update_workspace`:
  reject unknown keys / non-bool values in `settings.workflow` (400 "Unknown workflow switch"); because the jsonb `||`
  merge is shallow, merge `workflow` with the saved object in Python before writing.
- [ ] Commit `feat(wf): WF-01 tenant workflow switches`.

### W.2 — Engagement types table incl. E2E (WF-07)
**Files:** migration `supabase/migrations/20261015000100_engagement_types.sql`; the 19 files that branch on `c2c`
(`grep -rnE "'c2c'|\"c2c\"" apps supabase` — 49 hits).

- [ ] Migration:

```sql
create table mytrakin.engagement_types (
  code       text primary key,
  name       text not null,
  pay_model  text not null check (pay_model in ('payroll', 'vendor', 'self')),  -- W-2 / employer company / 1099
  is_active  boolean not null default true,
  sort       int not null default 0
);
insert into mytrakin.engagement_types (code, name, pay_model, sort) values
  ('w2_fulltime', 'W-2 full-time', 'payroll', 1), ('w2_contract', 'W-2 contract', 'payroll', 2),
  ('c2c', 'C2C (corp-to-corp)', 'vendor', 3), ('e2e', 'E2E (employer-to-employer)', 'vendor', 4),
  ('1099', '1099 contractor', 'self', 5);
alter table mytrakin.consultants drop constraint consultants_engagement_check;   -- confirm the generated name
alter table mytrakin.consultants add constraint consultants_engagement_fk
  foreign key (engagement) references mytrakin.engagement_types (code);
alter table mytrakin.consultants drop constraint consultants_c2c_employer;
-- ponytail: still lists vendor codes; a trigger reading pay_model is the upgrade if more vendor types appear
alter table mytrakin.consultants add constraint consultants_vendor_employer
  check (engagement not in ('c2c', 'e2e') or employer_company_id is not null);
grant select on mytrakin.engagement_types to mytrakin_api;   -- global read-only lookup (no tenant_id)
```
- [ ] API: `GET /engagement-types`. Replace `c2c`-specific business branches with `pay_model` (load
  `{code: pay_model}` once per request): consultant checklists (E2E gets the C2C list), W-2 → no AP payee
  (`pay_model == 'payroll'`), `timesheet_checks.py` overtime (payroll), compliance, CSV import accepts "E2E",
  `public.py`. Web: `label()` entries + any c2c filter lists include `e2e`; consultant form loads `/engagement-types`.
- [ ] Tests: E2E consultant with employer → 201, without → 400; E2E placement needs an AP vendor; E2E checklist == C2C.
- [ ] Commit `feat(wf): WF-07 engagement types table with E2E`.

### W.3 — Naming engine (WF-08)
**Files:** create `apps/api/app/services/numbering.py`, `apps/api/tests/test_numbering.py`; modify
`services/invoicing.py:21-24`, `routers/esign.py:108`, `routers/projects.py` (`_suggest_project_code`),
`routers/contracts.py` (agreement/SOW `code` optional → generated), `admin.py` (validate templates).

- [ ] Unit test (pure, runs without DB):

```python
from datetime import date

import pytest

from app.services.numbering import format_code


def test_templates():
    d = date(2026, 10, 15)
    assert format_code("PROJ-{YEAR}-{SEQ:3}", 7, d, {}) == "PROJ-2026-007"
    assert format_code("INV-{YYYYMM}-{SEQ}", 12, d, {}) == "INV-202610-12"
    assert format_code("MSA-{CLIENT}-{SEQ:2}", 3, d, {"CLIENT": "Northwind & Co"}) == "MSA-NORTHWINDCO-03"
    with pytest.raises(ValueError):
        format_code("X-{NOPE}", 1, d, {})
```
- [ ] `services/numbering.py`:

```python
"""Per-tenant document numbers from templates in tenants.settings.numbering (WF-08).

Placeholders: {YEAR} {YY} {MM} {YYYYMM} {SEQ} {SEQ:n} (zero-padded) plus any the caller passes ({CLIENT}, {PROJECT}).
A new entity type is a new key; its counter is mytrakin.next_number(tenant, key)."""

from __future__ import annotations

import re
from datetime import date

DEFAULTS = {   # today's formats, so nothing changes until an admin edits them
    "project": "PRJ-{SEQ:2}", "msa": "MSA-{CLIENT}-{SEQ:3}", "nda": "NDA-{CLIENT}-{SEQ:3}",
    "sow": "SOW-{PROJECT}-{SEQ:3}", "contract": "CON-{YEAR}-{SEQ:4}",
    "invoice_ar": "AR-{YEAR}-{SEQ:4}", "invoice_ap": "AP-{YEAR}-{SEQ:4}", "envelope": "ENV-{SEQ:5}",
}
COUNTER_KEYS = {"invoice_ar": "inv_AR", "invoice_ap": "inv_AP"}   # keep existing counters so numbers don't restart
_TOKEN = re.compile(r"\{([A-Z]+)(?::(\d+))?\}")


def format_code(template: str, seq: int, today: date, values: dict[str, str]) -> str:
    def sub(m: re.Match) -> str:
        name, width = m.group(1), m.group(2)
        builtin = {"YEAR": f"{today:%Y}", "YY": f"{today:%y}", "MM": f"{today:%m}", "YYYYMM": f"{today:%Y%m}",
                   "SEQ": str(seq).zfill(int(width or 0))}
        if name in builtin:
            return builtin[name]
        if name in values:
            return re.sub(r"[^A-Z0-9]+", "", str(values[name]).upper())[:12]
        raise ValueError(f"Unknown placeholder {{{name}}}")
    return _TOKEN.sub(sub, template)


async def next_code(db, entity: str, **values: str) -> str:
    saved = await db.val("select settings -> 'numbering' ->> :e from tenants where id = :t",
                         {"e": entity, "t": db.ctx.tenant_id})
    seq = await db.val("select mytrakin.next_number(:t, :k)", {"t": db.ctx.tenant_id, "k": COUNTER_KEYS.get(entity, entity)})
    return format_code(saved or DEFAULTS[entity], seq, date.today(), values)
```
  Note: the current project code logic suggests "highest number + 1" from existing codes; switching to a counter is
  fine — seed the `project` counter from the highest existing number in the W.3 migration
  (`insert into mytrakin.counters … on conflict do update set value = greatest(...)`).
- [ ] `PATCH /workspace` validates each `settings.numbering` template (`format_code(t, 1, today, {"CLIENT": "X",
  "PROJECT": "X"})`, must contain `{SEQ`) → 400 otherwise. Integration test: set `numbering.project =
  "PROJ-{YEAR}-{SEQ:3}"`, create a project without a code → `^PROJ-\d{4}-\d{3}$`; restore.
- [ ] Commit `feat(wf): WF-08 configurable naming engine`.

### W.4 — SOW belongs to a project; resources under a SOW (WF-04)
**Files:** migration `20261015000200_sow_project.sql`; `routers/contracts.py`, `routers/projects.py`.

- [ ] Migration (nullable on purpose — imported SOWs without a project stay valid):

```sql
alter table mytrakin.sows add column project_id uuid references mytrakin.projects (id);
create index sows_project_idx on mytrakin.sows (project_id);
update mytrakin.sows s set project_id = sub.project_id
  from (select distinct on (sow_id) sow_id, project_id
          from (select ar_sow_id as sow_id, project_id, start_date from mytrakin.placements where ar_sow_id is not null
                union all
                select ap_sow_id, project_id, start_date from mytrakin.placements where ap_sow_id is not null) x
         order by sow_id, start_date) sub
 where sub.sow_id = s.id and s.project_id is null;
```
- [ ] API: `SowIn.project_id: UUID | None`; `POST /projects/{id}/sows` = `add_sow` with `project_id` forced;
  `GET /projects/{id}` lists SOWs by `sows.project_id` (plus old placement-linked ones); `GET /sows/{id}/resources` =
  placements where `ar_sow_id = :id or ap_sow_id = :id`, through `placement_view` (masking); `POST /sows/{id}/resources`
  = `create_placement` with the SOW preset on its side and `project_id` from the SOW (400 if the SOW has no project or the
  body names another project).
- [ ] Tests: one SOW with two resources (Ravi + new E2E consultant) → 2 rows, each with its own AP contract; one SOW
  with one resource; cross-project placement → 400.
- [ ] Commit `feat(wf): WF-04 SOWs under projects with one or many resources`.

### W.5 — NDA → MSA → project gates (WF-02, WF-03, AGR-09)
**Files:** `services/workflow.py`, `contracts.py`, `projects.py`, `services/invoicing.py`, `invoices.py`,
`supabase/seed.sql` (active NDAs for Atlas, Northwind, Meridian, BrightPath, Orion so CI stays green).

| Action | Needs (only when the switch is on) |
|---|---|
| Create/activate MSA or subcontract with a company | active NDA with that company (`requireNDA`) |
| Project created `active` or PATCHed to `active` | client (and prime) NDA (`requireNDA`) + MSA (`requireMSA`) |
| Add SOW under an agreement | agreement active and unexpired (always) |
| Generate / create AR invoice | customer MSA active (`requireMSA`) |
| AP invoice in generation; AP payment | vendor subcontract or 1099 ICA active (`requireMSA`) |

Client payments *received* are always recorded (refusing cash that arrived would corrupt the ledger). Code from gaps
plan Task 1 (generate returns `blocked`, manual invoice 409, AP payment 409, add_sow 409), using
`has_active_agreement(kinds=...)` and `workflow.rules`.
- [ ] Tests: switch on → 409 `nda_required` / `msa_required`; switch off → allowed; terminated MSA blocks manual AR
  invoice; expired MSA blocks new SOW. Restore switches/status in `finally`.
- [ ] Commit `feat(wf): WF-02/03 NDA and MSA gates, AGR-09`.

### W.6 — Acceptance records + resource-contract gate (WF-05, WF-06)
**Files:** migration `20261015000300_acceptances.sql`; create `apps/api/app/routers/acceptances.py`; `public.py`
(`_complete`), `timesheets.py`, `main.py`.

- [ ] Migration:

```sql
create table mytrakin.acceptances (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references mytrakin.tenants (id) on delete cascade,
  entity_type  text not null check (entity_type in ('agreement', 'sow', 'amendment', 'placement')),
  entity_id    uuid not null,
  accepted_by  text not null,
  accepted_at  timestamptz not null default now(),
  method       text not null check (method in ('esign', 'manual')),
  envelope_id  uuid references mytrakin.envelopes (id),
  note         text,
  created_by   uuid
);
create index acceptances_entity_idx on mytrakin.acceptances (tenant_id, entity_type, entity_id);
alter table mytrakin.acceptances enable row level security;
create policy acceptances_read on mytrakin.acceptances for select to mytrakin_api using (is_internal());
create policy acceptances_write on mytrakin.acceptances for insert to mytrakin_api
  with check (can('legal') or can('account_manager') or current_setting('mytrakin.role', true) = 'system');
```
  Match the helper names/patterns in `20261011000400_security.sql` (`is_internal()`, `can()`, how `system` is
  expressed) and add the table to the audit trigger list there (new migration, same loop).
- [ ] `_complete` inserts an acceptance (method `esign`, signer names, envelope id) for the agreement / SOW / amendment.
  `POST /acceptances` {entity_type, entity_id, accepted_by, note} (legal/AM) records a paper acceptance and sets the
  agreement/SOW `active`; `GET /acceptances?entity_type=&entity_id=` returns history.
- [ ] Gate in `submit_my_week` and `approve`, per placement on the week: `requireContract` → vendor/self engagement needs
  `ap_sow_id`, payroll needs an `offer_letter` agreement for the consultant; `requireAcceptance` → client SOW and the
  contract are `active` with an acceptance row. 409 `contract_required` / `acceptance_required` naming the project.
- [ ] Tests: placement without AP contract → submit 409; switch off → 200; manual acceptance → history 1 row.
- [ ] Commit `feat(wf): WF-05/06 acceptance records and resource-contract gate`.

### W.7 — Payment status + confirmation (WF-09)
**Files:** migration `20261015000400_payment_confirmation.sql`; `services/invoicing.py`, `invoices.py`.

- [ ] Migration:

```sql
alter table mytrakin.payments
  add column status text not null default 'completed'
    check (status in ('pending', 'processing', 'completed', 'confirmed')),
  add column confirmed_by uuid, add column confirmed_by_name text, add column confirmed_at timestamptz;
```
  Existing rows become `completed`. Recreate `invoice_balances` (copy its current definition from the migrations) so
  only `completed`/`confirmed` payments reduce the balance.
- [ ] `POST /payments/{id}/confirm`: AR receipts → finance; AP payouts → finance or the payee's `vendor_admin` (RLS
  limits rows). 409 unless `completed`. `POST /payments/{id}/status` (finance) pending→processing→completed.
  `GET /payments` returns status + confirmation.
- [ ] Tests: record → completed; vendor confirms own AP payment → confirmed with name/time; vendor can't confirm AR;
  double confirm → 409; `processing` doesn't reduce balance.
- [ ] Commit `feat(wf): WF-09 payment status and confirmation`.

### W.8 — Money-safety fixes
Gaps-plan Task 7 (no re-opening a timesheet whose hours are invoiced → 409 `already_invoiced`) and cron link
`/my/timesheets` → `/my/timesheet`. Commit `fix(ts): …`.

### W.9 — End-to-end workflow tests (WF-11)
`test_workflow.py::test_register_to_payment_confirmation[c2c|e2e|1099]` with switches on: approve registration → NDA
(manual acceptance) → MSA → project activate → SOW under project → resource + contract (acceptance) → timesheet
submit/approve → generate invoices → AR payment → confirm → AP payment → payee confirms. Same flow with all switches off
(skips NDA/acceptance). Multi-resource: two resources on one SOW invoiced and paid independently.

### W.10 — Minimal UI (after logic is green), then docs
Settings → **Workflow** (4 switches) and **Numbering** (template per entity with live preview); project detail →
**SOWs** + **Add SOW**, per SOW **Resources** + **Add resource**; agreement/SOW detail → **Record acceptance** + history;
payments → status chip + **Confirm payment**; consultant form → engagement from `/engagement-types`; gate 409s shown
with "Change in Settings → Workflow" for admins. Phone width + dark mode. Then PLAN §5.30 statuses, §9 line, CHANGELOG,
`docs/api-reference.md`, Mermaid ERD in `docs/technical.md`, memory.

## E-mail deliverables → where
Gap analysis / entity mapping → this file + PLAN §5.30 · DB changes + migration strategy → W.2–W.7 (additive, backfilled,
nullable) · API changes → per task · tests → per task + W.9 · deployment/rollback → migrations are additive; rollback =
redeploy previous Vercel builds, new columns/tables are ignored by old code · ERD → W.10.

## Deferred until after go-live
From `2026-10-15-contracts-projects-timesheets-gaps.md`: AGR-04 warnings, AGR-05 renewal, PRJ-03 chain diagram, TS-04
KPIs/remind, TS-06 history, TS-10 time off, ESG-02 templates (pull the NDA template forward if W.5 ends early).
