# MSA / SOW / Work orders / Projects / Timesheets — gap closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every open gap in the already-built Projects, MSA, SOW / work order and Timesheet modules so they match
`docs/prototype-spec.md` §6.6, §6.8–6.10 and PLAN IDs AGR-04/05/09, PRJ-03, TS-04/06/07/10, ESG-02.

**Architecture:** No new modules. "Work order" is the same record as a SOW (`sows` table, e.g. `WO-NW-0388`), so the SOW
tasks cover it. Each change is a small addition to an existing FastAPI router/service plus the matching Next.js page.
One new service file (e-sign templates). No migrations: MSA renewal is a new draft agreement that takes over when
signed; the "active agreement" rule reads the existing `agreements` table.

**Tech Stack:** FastAPI + raw SQL (`db.one/all/val/run`), Postgres RLS (Supabase), pytest + httpx against a real
database, Next.js 16 App Router client pages (`useApi`, `useAction`, `DataTable`), fpdf2.

---

## Ground rules for whoever executes this

- Read `CLAUDE.md`, `docs/PLAN.md` §0 (Definition of Done) and §1 (RULE-01…07) first. AR/AP only; amounts masked by role.
- **API tests need Postgres.** This Windows machine has none (no `psql`, no Docker). Tests run in CI ("API (lint + tests
  against real migrations)"). Locally: `apps/api/.venv/Scripts/ruff check apps/api` and `cd apps/web && npm run typecheck`.
  Push the branch and read CI with `gh run list -L 3` / `gh run view <id> --log-failed`. Push only when the user agrees.
- Tests share one seeded database and run in file order (`test_access` → `test_company_onboarding` →
  `test_contracts_timesheets` → `test_flows`). New tests must leave the seed as they found it (restore in `finally`).
- Branch `feat/agr-ts-gaps` off `main`. Never commit `apps/web/next-env.d.ts`. Don't kill the dev server on port 3000.

## File map

| File | Change |
|---|---|
| `apps/api/app/routers/companies.py` | Task 0: activation gate accepts `super_admin` |
| `apps/api/app/routers/onboarding.py` | Task 0: MOA message names "MOA" |
| `apps/api/tests/test_company_onboarding.py` | Task 0: owner lookup matches creator role |
| `apps/api/app/services/invoicing.py` | Task 1: `has_active_agreement`, generate skips blocked, AP payment blocked |
| `apps/api/app/routers/invoices.py` | Task 1: manual invoice blocked; generate returns `blocked` |
| `apps/api/app/routers/contracts.py` | Tasks 1–3: SOW under expired MSA blocked, SOW warnings, MSA warning + renew |
| `apps/web/src/app/(app)/contracts/sows/[id]/page.tsx` | Task 2 |
| `apps/web/src/app/(app)/contracts/agreements/[id]/page.tsx` | Task 3 |
| `apps/api/app/routers/projects.py` | Task 4: `/placements?project_id=` |
| `apps/web/src/app/(app)/projects/[id]/page.tsx` | Task 4: chain diagram |
| `apps/api/app/routers/timesheets.py` | Tasks 5–8 |
| `apps/api/app/routers/cron.py:128` | Task 5: fix broken `/my/timesheets` link |
| `apps/web/src/app/(app)/timesheets/page.tsx` | Tasks 5–6 |
| `apps/web/src/app/(app)/timesheets/[id]/page.tsx` | Task 7 |
| `apps/web/src/app/(app)/my/timesheet/page.tsx` | Task 8 |
| `apps/api/app/services/esign_templates.py` (new) | Task 9 |
| `apps/api/app/routers/esign.py`, `apps/web/src/app/(app)/esign/new/page.tsx` | Task 9 |
| `apps/api/tests/test_contracts_timesheets.py` (new) | Tasks 1–9 tests |
| `docs/PLAN.md`, `CHANGELOG.md`, `docs/api-reference.md` | Task 10 |

Test file header (create in Task 1; later tasks append tests):

```python
"""MSAs, SOWs / work orders, projects and timesheets: rules added to close PLAN gaps
AGR-04/05/09, PRJ-03, TS-04/06/07/10 and ESG-02."""

from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy import text

from app.db import get_engine

THIS_WEEK = date.today() - timedelta(days=(date.today().weekday() + 1) % 7)
OLD_WEEK = THIS_WEEK - timedelta(weeks=30)   # inside Ravi's placement (started 250 days ago), before seeded invoices


async def _sql(statement: str, **params) -> None:
    async with get_engine().begin() as conn:
        await conn.execute(text(statement), params)


async def _id(client, auth, path: str, field: str, value: str) -> str:
    rows = (await client.get(path, headers=auth("admin"))).json()
    return next(r["id"] for r in rows if r[field] == value)
```

---

### Task 0: Get CI green on main (baseline)

CI failed on the last 3 commits (`gh run view 38670331857 --log-failed`), 3 tests in `test_company_onboarding.py`:
1. `POST /companies` makes the creator `super_admin`, but the activation gate (`companies.py:440`) counts only `owner`
   → "Assign a company owner". Real bug: a Super Admin is the top owner.
2. `test_last_owner_is_protected_and_members_managed` looks up a member with role `owner` that no longer exists.
3. `onboarding.py:417` message "Upload the Memorandum of Association first" lacks "MOA".

- [ ] **Step 1:** `companies.py` ~line 440: `cm.company_role = 'owner'` → `cm.company_role in ('super_admin', 'owner')`.
- [ ] **Step 2:** `onboarding.py:417` → `raise ApiError(422, "moa_required", "Upload the Memorandum of Association (MOA) first")`.
- [ ] **Step 3:** In `test_company_onboarding.py` delete the `owner = next(...)` lookup (lines 110–111) and demote the
  invited owner instead:

```python
    demote = await client.patch(f"/companies/{cid}/members/{invited.json()['id']}", headers=admin,
                                json={"company_role": "member"})
```
  Confirm the add-member handler returns the member `id`; if not, find it in `GET /companies/{cid}/members` by
  `email == "finance@example.com"`.
- [ ] **Step 4:** ruff clean. **Step 5:** commit `fix(onboarding): Super Admin counts as owner for activation; MOA message;
  test owner lookup`; push branch; CI must be green before Task 1.

---

### Task 1: AGR-09 — no active agreement ⇒ no invoices, no vendor payments, no new SOWs

Rule (spec §6.6/§6.20): "No MSA — invoices and payments blocked"; "New SOWs and payments under it will be blocked after
expiry". An agreement counts when `status='active'`, kind `msa`/`subcontract`/`ica`, and the date is within
`effective_on..expires_on` (nulls open). **Decision:** client payments *received* are still recorded (refusing cash that
arrived would corrupt the ledger); only outgoing AP payments are blocked.

- [ ] **Step 1: Failing test** (create test file with header, then):

```python
async def test_no_active_msa_blocks_invoices_and_new_sows(client, auth):
    finance, admin = auth("finance"), auth("admin")
    ravi = next(p for p in (await client.get("/placements", headers=finance)).json() if p["consultant"] == "Ravi Kumar")
    await _sql("update mytrakin.agreements set status = 'terminated' where code = 'MSA-NW-ESG'")
    try:
        blocked = await client.post("/invoices", headers=finance, json={
            "placement_id": ravi["id"], "period_start": str(OLD_WEEK), "period_end": str(OLD_WEEK + timedelta(days=6)),
            "hours": 8, "send": False})
        assert blocked.status_code == 409 and "MSA" in blocked.text, blocked.text
    finally:
        await _sql("update mytrakin.agreements set status = 'active' where code = 'MSA-NW-ESG'")

    northwind = await _id(client, auth, "/companies", "name", "Northwind Consulting")
    old = await client.post("/agreements", headers=admin, json={
        "code": "MSA-NW-OLD", "kind": "msa", "company_id": northwind, "tenant_side": "supplier",
        "effective_on": str(date.today() - timedelta(days=400)), "expires_on": str(date.today() - timedelta(days=1))})
    assert old.status_code == 201, old.text
    sow = await client.post("/sows", headers=admin, json={
        "code": "WO-NW-OLD-1", "agreement_id": old.json()["id"], "side": "we_bill", "title": "Too late",
        "start_date": str(date.today()), "end_date": str(date.today() + timedelta(days=30))})
    assert sow.status_code == 409 and "expired" in sow.text, sow.text
```
- [ ] **Step 2:** CI/pytest → FAIL (201 instead of 409).
- [ ] **Step 3:** `services/invoicing.py`, after `next_invoice_number`:

```python
async def has_active_agreement(db: Db, *, company_id: Any = None, consultant_id: Any = None, on: date) -> bool:
    """An active MSA, subcontract or 1099 contractor agreement with this party covers the date."""
    return bool(await db.val(
        """select exists (select 1 from agreements
                           where status = 'active' and kind in ('msa', 'subcontract', 'ica')
                             and (company_id = cast(:co as uuid) or consultant_id = cast(:con as uuid))
                             and coalesce(effective_on, cast(:d as date)) <= :d
                             and coalesce(expires_on, cast(:d as date)) >= :d)""",
        {"co": company_id, "con": consultant_id, "d": on}))
```
- [ ] **Step 4:** `generate_invoices` returns `tuple[list[dict], list[str]]`: `blocked: list[str] = []` at top; inside the
  loop after the bill-rate check:

```python
        if not await has_active_agreement(db, company_id=row["ar_company_id"], on=period_end):
            name = await db.val("select name from companies where id = :id", {"id": row["ar_company_id"]})
            blocked.append(f"{name}: no active MSA")
            continue
```
  and inside `if payee and row["pay_rate"] is not None:` before the AP insert:

```python
            if not await has_active_agreement(db, company_id=row["ap_company_id"], consultant_id=row["ap_consultant_id"],
                                              on=period_end):
                blocked.append(f"Payable for placement {row['placement_id']}: no active vendor or contractor agreement")
                continue
```
  `return created, blocked`. Only caller `routers/invoices.py:131`:

```python
    created, blocked = await generate_invoices(db, tenant_id=db.ctx.tenant_id, user_id=db.ctx.user_id,
                                               period_start=body.period_start, period_end=body.period_end, issue_on=body.issue_on)
    return {"created": created, "blocked": blocked}
```
- [ ] **Step 5:** `create_invoice` (invoices.py), after the bill-rate check:

```python
    if not await has_active_agreement(db, company_id=p["ar_company_id"], on=body.period_end):
        raise conflict(f"{p['customer']} has no active MSA — invoices are blocked until one is signed")
```
  (import `has_active_agreement` and `conflict`).
- [ ] **Step 6:** `record_payment` (invoicing.py), after the held/exception check:

```python
    if invoice["direction"] == "ap" and not await has_active_agreement(
            db, company_id=invoice["company_id"], consultant_id=invoice["consultant_id"], on=paid_on):
        raise conflict("No active agreement with this payee — vendor payments are blocked until one is signed")
```
  Confirm `invoice_balances` exposes `company_id`/`consultant_id` (`grep -n "invoice_balances" -A 20 supabase/migrations/*.sql`).
- [ ] **Step 7:** `add_sow` (contracts.py): select `status` too; after not-found:

```python
    if agreement["status"] in ("expired", "terminated") or (agreement["expires_on"] and agreement["expires_on"] < date.today()):
        raise conflict("This agreement has expired — renew it before adding SOWs under it")
```
- [ ] **Step 8: Web:** `grep -rn "invoices/generate" apps/web/src`; append `r.blocked.length ? \` Skipped: ${r.blocked.join("; ")}\` : ""`
  to the message shown.
- [ ] **Step 9:** ruff + typecheck; CI: new test and `test_timesheet_to_invoice_to_payment` pass (seed agreements active).
- [ ] **Step 10:** commit `feat(agr): AGR-09 block invoices, vendor payments and new SOWs without an active agreement`.

---

### Task 2: AGR-04 — SOW detail warnings

Spec: "This SOW runs past the upstream SOW it supports." / "A downstream vendor SOW ends before this one — extend it
before the consultant's term runs out."; masked → "Values are hidden for your role."

- [ ] **Step 1: Failing test**

```python
async def test_sow_flow_down_warnings(client, auth):
    admin = auth("admin")
    msa_nw = await _id(client, auth, "/agreements", "code", "MSA-NW-ESG")
    msa_bp = await _id(client, auth, "/agreements", "code", "MSA-ESG-BP")
    today = date.today()
    up_sow = (await client.post("/sows", headers=admin, json={
        "code": "WO-T-UP", "agreement_id": msa_nw, "side": "we_bill", "title": "Upstream",
        "start_date": str(today), "end_date": str(today + timedelta(days=200))})).json()
    down_sow = (await client.post("/sows", headers=admin, json={
        "code": "SOW-T-DOWN", "agreement_id": msa_bp, "side": "we_pay", "title": "Downstream",
        "start_date": str(today), "end_date": str(today + timedelta(days=100)), "flows_from_sow_id": up_sow["id"]})).json()

    up = (await client.get(f"/sows/{up_sow['id']}", headers=admin)).json()
    assert any("downstream vendor SOW ends before" in w for w in up["warnings"]), up["warnings"]
    await _sql("update mytrakin.sows set end_date = current_date + 50 where id = :id", id=up_sow["id"])
    down = (await client.get(f"/sows/{down_sow['id']}", headers=admin)).json()
    assert "This SOW runs past the upstream SOW it supports." in down["warnings"], down["warnings"]
```
- [ ] **Step 2:** FAIL (`KeyError: 'warnings'`).
- [ ] **Step 3:** `get_sow`, after `sow["flows_to"] = ...`:

```python
    warnings = []
    upstream_end = await db.val("select fs.end_date from sows s join sows fs on fs.id = s.flows_from_sow_id where s.id = :id",
                                {"id": sow_id})
    if upstream_end and sow["end_date"] > upstream_end:
        warnings.append("This SOW runs past the upstream SOW it supports.")
    if any(f["end_date"] < sow["end_date"] for f in sow["flows_to"]):
        warnings.append("A downstream vendor SOW ends before this one — extend it before the consultant's term runs out.")
    sow["warnings"] = warnings
```
- [ ] **Step 4: Web** (`sows/[id]/page.tsx`): before `<div className="grid k4">` add
  `{s.warnings.map((w: string) => <p key={w} className="err">{w}</p>)}` and wrap the KPI grid:
  `{s.value_cap === null && s.invoiced === null ? <p className="muted">Values are hidden for your role.</p> : (<div className="grid k4">…existing cards…</div>)}`.
- [ ] **Step 5:** CI + typecheck. **Step 6:** commit `feat(agr): AGR-04 SOW flow-down warnings and masked value note`.

---

### Task 3: AGR-05 — MSA expiry warning + Start renewal

Spec: ≤ 90 days → "Expires in n days, before some/none of its SOWs end. New SOWs and payments under it will be blocked
after expiry."; **Start renewal** (admin/legal). Design: renewal = new draft `<CODE>-R<n>` (same party/terms) effective
the day after current expiry; user goes to Send for signature; on completion the existing code sets it active and
`has_active_agreement` covers dates after the old expiry.

- [ ] **Step 1: Failing test**

```python
async def test_msa_expiry_warning_and_renewal(client, auth):
    admin = auth("admin")
    msa_od = await _id(client, auth, "/agreements", "code", "MSA-ESG-OD")   # seed: expires in 81 days
    detail = (await client.get(f"/agreements/{msa_od}", headers=admin)).json()
    assert detail["warning"].startswith("Expires in 81 days"), detail.get("warning")
    expiry = date.fromisoformat(detail["expires_on"])
    assert (await client.post(f"/agreements/{msa_od}/renew", headers=admin,
                              json={"expires_on": str(expiry)})).status_code == 400
    renewal = await client.post(f"/agreements/{msa_od}/renew", headers=admin,
                                json={"expires_on": str(expiry + timedelta(days=365))})
    assert renewal.status_code == 201, renewal.text
    body = renewal.json()
    assert body["code"] == "MSA-ESG-OD-R1" and body["status"] == "draft"
    assert body["effective_on"] == str(expiry + timedelta(days=1))
    assert (await client.post(f"/agreements/{msa_od}/renew", headers=auth("finance"),
                              json={"expires_on": str(expiry + timedelta(days=365))})).status_code == 403
```
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** `get_agreement`, before `return row`:

```python
    row["days_left"] = (row["expires_on"] - date.today()).days if row["expires_on"] else None
    if row["days_left"] is not None and row["days_left"] <= 90:
        outlives = any(s["end_date"] and s["end_date"] > row["expires_on"] for s in row["sows"])
        row["warning"] = (f"Expires in {row['days_left']} days, before {'some' if outlives else 'none'} of its SOWs end. "
                          "New SOWs and payments under it will be blocked after expiry.")
```
  New endpoint:

```python
class RenewalIn(BaseModel):
    expires_on: date


@router.post("/agreements/{agreement_id}/renew", status_code=201)
async def start_renewal(agreement_id: UUID, body: RenewalIn, db: TenantDb = Depends(tenant_db)):
    """Draft the renewal (same party and terms, starting when the current one ends) to send for signature."""
    db.ctx.require("legal")
    old = await db.one("select * from agreements where id = :id", {"id": agreement_id})
    if old is None:
        raise not_found("Agreement")
    starts = old["expires_on"] + timedelta(days=1) if old["expires_on"] else date.today()
    if body.expires_on <= starts:
        raise bad_request("The renewal has to end after the current agreement")
    n = await db.val("select count(*) from agreements where code like :p", {"p": f"{old['code']}-R%"})
    return await db.one(
        """insert into agreements (tenant_id, code, kind, company_id, consultant_id, tenant_side, effective_on, expires_on,
                                   payment_terms, renewal, notice_period, insurance_required, status, source)
           values (:t, :code, :kind, :co, :con, :side, :eff, :exp, :terms, :renew, :notice, :ins, 'draft', 'myTrakIn')
           returning *""",
        {"t": db.ctx.tenant_id, "code": f"{old['code']}-R{n + 1}", "kind": old["kind"], "co": old["company_id"],
         "con": old["consultant_id"], "side": old["tenant_side"], "eff": starts, "exp": body.expires_on,
         "terms": old["payment_terms"], "renew": old["renewal"], "notice": old["notice_period"],
         "ins": old["insurance_required"]})
```
- [ ] **Step 4: Web** (`agreements/[id]/page.tsx`): import `useState`, `Field`, `formValues`, `Modal`, `useAction`, `api`;
  hooks `const [renewing, setRenewing] = useState(false); const { run, busy } = useAction();` **before** early returns.
  Render `{a.warning && <p className="err">{a.warning}</p>}`; Expires `<dd>{date(a.expires_on)}{a.days_left !== null && \` (${a.days_left} days)\`}</dd>`;
  action `{allows(workspace, "legal") && a.kind !== "nda" && <button className="btn" onClick={() => setRenewing(true)}>Start renewal</button>}`; modal:

```tsx
      {renewing && (
        <Modal title={`Renew ${a.code}`} onClose={() => setRenewing(false)}>
          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            const r = await run(() => api(`/agreements/${id}/renew`, { body: formValues(e.currentTarget) }), "Renewal drafted — send it for signature");
            if (r) router.push(`/esign/new?agreement_id=${r.id}&title=${encodeURIComponent(`${label(r.kind)} ${r.code} (renewal)`)}`);
          }}>
            <Field label="New expiry date" name="expires_on" type="date" required />
            <p className="note">Same party and terms. It starts the day after {date(a.expires_on)} and becomes active once everyone signs.</p>
            <button className="btn pri mt" disabled={busy}>Draft renewal</button>
          </form>
        </Modal>
      )}
```
- [ ] **Step 5:** CI + typecheck. **Step 6:** commit `feat(agr): AGR-05 MSA expiry warning and Start renewal`.

---

### Task 4: PRJ-03 — chain diagram per placement on project detail

Spec §6.9: [End client `••••` "Not our contract · Not tracked"] → Customer → **AR** rate/hr · doc · terms → **Us** →
**AP** rate/hr · doc · terms → Vendor / 1099 → Consultant; W-2 → "W-2 payroll" → Employee. Rates come masked from
`placement_view`. CSS `.chain/.node/.link` already exists.

- [ ] **Step 1: Failing test**

```python
async def test_placements_filter_by_project_and_mask_rates(client, auth):
    project = next(p for p in (await client.get("/projects", headers=auth("admin"))).json() if p["name"] == "S/4 Security Rollout")
    rows = (await client.get("/placements", params={"project_id": project["id"]}, headers=auth("finance"))).json()
    assert rows and all(r["project_id"] == project["id"] for r in rows)
    assert any(r["bill_rate"] is not None for r in rows)
    hidden = (await client.get("/placements", params={"project_id": project["id"]}, headers=auth("vendor"))).json()
    assert all(r["bill_rate"] is None for r in hidden)
```
- [ ] **Step 2:** FAIL (filter ignored).
- [ ] **Step 3:**

```python
@router.get("/placements")
async def list_placements(db: TenantDb = Depends(tenant_db), status: str | None = None, project_id: UUID | None = None):
    rows = await db.all(_PLACEMENT_SQL + """ where (cast(:s as text) is null or p.status = :s)
                                               and (cast(:pr as uuid) is null or p.project_id = :pr)
                                             order by c.full_name, p.start_date desc""",
                        {"s": status, "pr": project_id})
    return [placement_view(r, db.ctx) for r in rows]
```
- [ ] **Step 4: Web** (`projects/[id]/page.tsx`): `const placements = useApi<any[]>("/placements", { project_id: id });`
  before early returns; import `money`; card after the `grid c2` block:

```tsx
      <div className="card mt">
        <h3>Placements &amp; chain</h3>
        <p className="note">You track only your own two links: the bill rate to your customer (AR) and the pay rate to your vendor or contractor (AP). Rates between other parties are never stored.</p>
        {(placements.data ?? []).map((pl) => <Chain key={pl.id} pl={pl} us={workspace?.tenant.name ?? "Us"} />)}
        {placements.data?.length === 0 && <p className="muted">No placements on this project.</p>}
      </div>
```
  and at file bottom:

```tsx
function Chain({ pl, us }: { pl: any; us: string }) {
  const rate = (r: any) => (r === null || r === undefined ? "••••" : `${money(r)}/hr`);
  const w2 = String(pl.engagement).startsWith("w2");
  const Rate = ({ side, r, doc, terms }: any) => (
    <div className="link"><div>{side}</div><div className="r">{rate(r)}</div><div className="arr" /><div>{[doc, terms].filter(Boolean).join(" · ")}</div></div>
  );
  return (
    <div className="mt">
      <b>{pl.consultant}</b> · <Chip status={pl.status} /> · {label(pl.engagement)} · {pl.role_title}
      <div className="chain">
        {pl.end_client && pl.end_client !== pl.ar_company && <>
          <div className="node"><div className="t">End client</div><div className="n">{pl.end_client}</div></div>
          <div className="link"><div className="r">••••</div><div className="arr" /><div>Not our contract · Not tracked</div></div>
        </>}
        <div className="node"><div className="t">Customer</div><div className="n">{pl.ar_company ?? "–"}</div></div>
        <Rate side="AR" r={pl.bill_rate} doc={pl.ar_sow} terms={pl.ar_terms} />
        <div className="node esg"><div className="t">Us</div><div className="n">{us}</div></div>
        {w2 ? <>
          <div className="link"><div>W-2 payroll</div><div className="arr" /></div>
          <div className="node"><div className="t">Employee</div><div className="n">{pl.consultant}</div></div>
        </> : <>
          <Rate side="AP" r={pl.pay_rate} doc={pl.ap_sow} terms={pl.pay_when_paid ? "Pay-when-paid" : pl.ap_terms} />
          <div className="node"><div className="t">{pl.ap_consultant ? "1099 contractor" : "Vendor"}</div><div className="n">{pl.ap_company ?? pl.ap_consultant ?? "–"}</div></div>
          {pl.ap_company && <><div className="link"><div>{label(pl.engagement)}</div><div className="arr" /></div>
            <div className="node"><div className="t">Consultant</div><div className="n">{pl.consultant}</div></div></>}
        </>}
      </div>
    </div>
  );
}
```
- [ ] **Step 5:** typecheck; check phone width + dark mode in the app. **Step 6:** commit `feat(prj): PRJ-03 placement chain diagram`.

---

### Task 5: TS-04 — approver KPIs + "Remind n not submitted" (+ broken reminder link)

Spec §6.10 KPIs: Waiting for approval · Approved ("Locked — feeding AR and AP") · Not submitted ("Reminders running") ·
Flagged by checks ("Review before approving"); buttons "Approve n that pass all checks", "Remind n not submitted".
Found: cron e-mail links to `/my/timesheets?week=…`; the page is `/my/timesheet` (404).

- [ ] **Step 1: Failing test**

```python
async def test_remind_not_submitted(client, auth):
    reminded = await client.post("/timesheets/remind", params={"week": str(THIS_WEEK)}, headers=auth("finance"))
    assert reminded.status_code == 200, reminded.text
    assert isinstance(reminded.json()["reminded"], list)
    assert (await client.post("/timesheets/remind", params={"week": str(THIS_WEEK)}, headers=auth("vendor"))).status_code == 403
```
- [ ] **Step 2:** FAIL (route missing).
- [ ] **Step 3:** `timesheets.py` imports `from ..config import get_settings`, `from ..services.email import render, send_email`;
  **above** `@router.get("/{timesheet_id}")`:

```python
@router.post("/remind")
async def remind_not_submitted(db: TenantDb = Depends(tenant_db), week: date = Query(...)):
    """E-mail everyone scheduled that week who hasn't submitted yet (once per person per day)."""
    db.ctx.require(*APPROVER_ROLES)
    ws = _sunday(week)
    reminded = []
    for r in (await week_overview(db, ws))["rows"]:
        if r["status"] in ("submitted", "approved"):
            continue
        email = await db.val("select email from consultants where id = :id", {"id": r["consultant_id"]})
        if email and await send_email(
                db, to=[email], subject=f"Reminder: timesheet for the week of {ws:%b %d}", kind="timesheet_reminder",
                tenant_id=db.ctx.tenant_id, ref_type="consultant", ref_id=r["consultant_id"],
                dedupe_key=f"ts-manual:{r['consultant_id']}:{ws}:{date.today()}",
                html_body=render(f"Hi {r['full_name'].split()[0]}, please submit your timesheet",
                                 [f"Your timesheet for the week of {ws:%B %d} hasn't been submitted.",
                                  "Approved hours are what we invoice and pay from, so late timesheets delay payments."],
                                 button=("Open my timesheet", f"{get_settings().web_origin}/my/timesheet"))):
            reminded.append(r["full_name"])
    return {"reminded": reminded}
```
  `cron.py:128`: `/my/timesheets?week={week}` → `/my/timesheet`.
- [ ] **Step 4: Web** (`timesheets/page.tsx`):

```tsx
  const rowsNow = data?.rows ?? [];
  const count = (f: (r: any) => boolean) => rowsNow.filter(f).length;
  const notSubmitted = count((r) => !["submitted", "approved"].includes(r.status));
  const flagged = count((r) => r.status === "submitted" && r.checks && r.checks.result !== "pass");
```
  KPI grid at top of the week tab:

```tsx
          <div className="grid k4">
            <div className="card kpi"><div className="l">Waiting for approval</div><div className="v">{count((r) => r.status === "submitted")}</div></div>
            <div className="card kpi"><div className="l">Approved</div><div className="v">{count((r) => r.status === "approved")}</div><div className="muted">Locked — feeding AR and AP</div></div>
            <div className="card kpi"><div className="l">Not submitted</div><div className="v">{notSubmitted}</div><div className="muted">Reminders running</div></div>
            <div className="card kpi"><div className="l">Flagged by checks</div><div className="v">{flagged}</div><div className="muted">Review before approving</div></div>
          </div>
```
  Actions (wrap in fragment) add:

```tsx
          <button className="btn" disabled={busy || !notSubmitted} onClick={async () => {
            const r = await run(() => api("/timesheets/remind", { method: "POST", query: { week } }));
            if (r) alert(r.reminded.length ? `Reminded: ${r.reminded.join(", ")}` : "No one to remind (no e-mail on file or already reminded today)");
          }}>Remind {notSubmitted} not submitted</button>
```
  Approve label → `Approve {passing} that pass all checks`. Footer note → "Reminders go out Friday 3:00 PM and Monday
  9:00 AM until a timesheet is submitted. Approved timesheets lock; corrections need an adjustment that the admin approves
  again." + existing overtime sentence.
- [ ] **Step 5:** CI + typecheck. **Step 6:** commit `feat(ts): TS-04 KPIs and Remind not submitted; fix reminder link`.

---

### Task 6: TS-06 — history: Approved by, Billing, KPIs

Spec: KPIs Timesheet lines ("One per consultant, week and project"), Approved hours, Consultants, Projects; columns
… Approved by, Billing (Invoiced and paid / Invoiced <month> / In next invoice / Internal — not billed). CSV exists in DataTable.

- [ ] **Step 1: Failing test**

```python
async def test_history_has_approver_and_billing(client, auth):
    rows = (await client.get("/timesheets/history", headers=auth("finance"))).json()
    assert rows and {"approved_by", "billing"} <= rows[0].keys()
    assert all(r["billing"] == "Internal — not billed" for r in rows if r["project"] == "Internal")
```
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** replace the `history` query:

```python
    rows = await db.all(
        """select t.id, t.week_start, t.status, c.full_name, c.id as consultant_id, coalesce(pr.name, 'Internal') as project,
                  sum(e.hours) as hours, t.decided_at, dp.full_name as approved_by, e.placement_id,
                  inv.issued_on as invoiced_on, inv.live_status as invoice_status
             from timesheets t join consultants c on c.id = t.consultant_id
             join timesheet_entries e on e.timesheet_id = t.id
             left join placements p on p.id = e.placement_id left join projects pr on pr.id = p.project_id
             left join profiles dp on dp.id = t.decided_by and t.status = 'approved'
             left join lateral (select i.issued_on, i.live_status from invoice_balances i
                                 where i.placement_id = e.placement_id and i.direction = 'ar' and i.live_status <> 'void'
                                   and i.period_start <= t.week_start + 6 and i.period_end >= t.week_start
                                 order by i.issued_on desc limit 1) inv on true
            where (cast(:c as uuid) is null or t.consultant_id = :c)
              and (cast(:f as date) is null or t.week_start >= :f) and (cast(:u as date) is null or t.week_start <= :u)
            group by t.id, c.id, pr.name, dp.full_name, e.placement_id, inv.issued_on, inv.live_status
            order by t.week_start desc, c.full_name, project
            limit 2000""",
        {"c": consultant_id, "f": since, "u": until})
    for r in rows:
        if r["placement_id"] is None:
            r["billing"] = "Internal — not billed"
        elif r["invoiced_on"]:
            r["billing"] = "Invoiced and paid" if r["invoice_status"] == "paid" else f"Invoiced {r['invoiced_on']:%b}"
        else:
            r["billing"] = "In next invoice" if r["status"] == "approved" else "–"
        del r["invoiced_on"], r["invoice_status"]
    return rows
```
- [ ] **Step 4: Web:** history columns add `{ key: "approved_by", label: "Approved by", hideSm: true }, { key: "billing", label: "Billing", filter: true }`;
  KPI grid above the table (import `num`):

```tsx
        <div className="grid k4">
          <div className="card kpi"><div className="l">Timesheet lines</div><div className="v">{history.data?.length ?? 0}</div><div className="muted">One per consultant, week and project</div></div>
          <div className="card kpi"><div className="l">Approved hours</div><div className="v">{num((history.data ?? []).filter((r) => r.status === "approved").reduce((s, r) => s + Number(r.hours), 0), 2)}</div></div>
          <div className="card kpi"><div className="l">Consultants</div><div className="v">{new Set((history.data ?? []).map((r) => r.consultant_id)).size}</div></div>
          <div className="card kpi"><div className="l">Projects</div><div className="v">{new Set((history.data ?? []).map((r) => r.project)).size}</div></div>
        </div>
```
- [ ] **Step 5:** CI + typecheck. **Step 6:** commit `feat(ts): TS-06 history approved-by, billing and KPIs`.

---

### Task 7: TS-07 — adjustment after approval

`POST /timesheets/{id}/reject` already reopens approved weeks, but even when invoiced — and `approved_hours_by_placement`
skips periods that already have an AR invoice, so the change is silently lost. Rule: reopen only while none of the week's
hours are invoiced; invoiced weeks need void/credit first (credit notes = PLAN Phase 1).

- [ ] **Step 1: Failing test**

```python
async def test_adjustment_only_before_invoicing(client, auth):
    consultant, finance = auth("consultant"), auth("finance")
    week = (await client.get("/timesheets/mine", params={"week": str(OLD_WEEK)}, headers=consultant)).json()
    assert week["status"] == "draft", week   # pick another OLD_WEEK if the seed already has this one
    rows = [{"placement_id": p["placement_id"], "hours": [0, 8, 8, 0, 0, 0, 0]} for p in week["projects"][:1]]
    assert (await client.put("/timesheets/mine", headers=consultant, json={"week_start": str(OLD_WEEK), "rows": rows})).status_code == 200
    ts = (await client.post("/timesheets/mine/submit", params={"week": str(OLD_WEEK)}, headers=consultant, json={})).json()
    assert (await client.post(f"/timesheets/{ts['id']}/approve", headers=finance)).status_code == 200

    reopened = await client.post(f"/timesheets/{ts['id']}/reject", headers=finance, json={"reason": "Tuesday was 6 hours"})
    assert reopened.status_code == 200 and reopened.json()["status"] == "rejected"
    rows[0]["hours"] = [0, 8, 6, 0, 0, 0, 0]
    assert (await client.put("/timesheets/mine", headers=consultant, json={"week_start": str(OLD_WEEK), "rows": rows})).status_code == 200
    await client.post("/timesheets/mine/submit", params={"week": str(OLD_WEEK)}, headers=consultant, json={})
    assert (await client.post(f"/timesheets/{ts['id']}/approve", headers=finance)).status_code == 200

    generated = await client.post("/invoices/generate", headers=finance, json={
        "period_start": str(OLD_WEEK), "period_end": str(OLD_WEEK + timedelta(days=6))})
    assert generated.json()["created"], generated.text
    late = await client.post(f"/timesheets/{ts['id']}/reject", headers=finance, json={"reason": "One more change"})
    assert late.status_code == 409 and "invoiced" in late.text, late.text
```
- [ ] **Step 2:** FAIL (last reject 200).
- [ ] **Step 3:** in `reject`, after the reason check:

```python
    invoiced = await db.val(
        """select exists (select 1 from timesheet_entries e
                            join invoices i on i.placement_id = e.placement_id and i.direction = 'ar' and i.status <> 'void'
                                           and i.period_start <= e.work_date and i.period_end >= e.work_date
                           where e.timesheet_id = :id)""", {"id": timesheet_id})
    if invoiced:
        raise ApiError(409, "already_invoiced", "These hours are already invoiced. Void or credit the invoice first, "
                                                "then request the adjustment.")
```
- [ ] **Step 4: Web** (`timesheets/[id]/page.tsx`): when `ts.status === "approved"` the button reads **Request adjustment**,
  prompt "What needs to change? The consultant corrects the week and it comes back to you for approval.", toast
  "Adjustment opened — changes need approval again"; under the grid for approved:
  `<p className="note">Approved{ts.decided_at && \` on ${date(ts.decided_at)}\`}. Locked.</p>`.
- [ ] **Step 5:** CI + typecheck. **Step 6:** commit `feat(ts): TS-07 request adjustment, blocked once invoiced`.

---

### Task 8: TS-10 — approved time off shown on the timesheet

Spec §7: "Approved time off is pre-filled on your timesheet…". Pre-fill = read-only "Time off (approved)" row (not saved
as hours; not billable). **Not done:** "client approver is notified" — `projects.client_approver` is free text with no
e-mail; record as 🟡 in PLAN.

- [ ] **Step 1: Failing test** (check `people_pay.Decision` field and `/time-off` prefix first):

```python
async def test_approved_time_off_shows_on_timesheet(client, auth):
    next_week = THIS_WEEK + timedelta(days=7)
    asked = await client.post("/me/time-off", headers=auth("consultant"), json={
        "starts_on": str(next_week + timedelta(days=1)), "ends_on": str(next_week + timedelta(days=2)), "kind": "pto"})
    assert asked.status_code == 201, asked.text
    decided = await client.post(f"/time-off/{asked.json()['id']}/decision", headers=auth("admin"), json={"decision": "approved"})
    assert decided.status_code == 200, decided.text
    week = (await client.get("/timesheets/mine", params={"week": str(next_week)}, headers=auth("consultant"))).json()
    assert week["time_off"] == [None, "pto", "pto", None, None, None, None]
```
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** `my_week`, before `return`:

```python
    off = await db.all(
        """select starts_on, ends_on, kind from time_off where consultant_id = :c and status in ('approved', 'holiday')
            and starts_on <= cast(:ws as date) + 6 and ends_on >= :ws""", {"c": db.ctx.consultant_id, "ws": ws})
    time_off = [next((o["kind"] for o in off if o["starts_on"] <= ws + timedelta(days=i) <= o["ends_on"]), None) for i in range(7)]
```
  add `"time_off": time_off` to the returned dict.
- [ ] **Step 4: Web** (`my/timesheet/page.tsx`, import `label`), before the Day total row:

```tsx
                {data.time_off?.some(Boolean) && (
                  <tr><td className="muted">Time off (approved)</td>
                    {data.time_off.map((k: string | null, di: number) => <td key={di} className="muted">{k ? label(k) : ""}</td>)}<td /></tr>
                )}
```
- [ ] **Step 5:** CI + typecheck. **Step 6:** commit `feat(ts): TS-10 approved time off on the weekly timesheet`.

---

### Task 9: ESG-02 — templates: Mutual NDA, Offer letter (W-2), ICA (1099)

`POST /envelopes` accepts `template` + `consultant_id`; API renders the PDF (fpdf2) and creates the matching draft
agreement (`nda`/`offer_letter`/`ica`) linked to the envelope, so existing completion code activates it when signed.
**Template wording is a starting draft — owner's counsel must approve before real use** (add to PLAN §6).

- [ ] **Step 1: Failing test**

```python
async def test_send_nda_from_template(client, auth):
    admin = auth("admin")
    ravi = await _id(client, auth, "/consultants", "full_name", "Ravi Kumar")
    signer = json.dumps([{"name": "Ravi Kumar", "email": "ravi@example.com"}])
    created = await client.post("/envelopes", headers=admin, data={
        "title": "Mutual NDA — Ravi Kumar", "template": "nda", "consultant_id": ravi, "signers": signer})
    assert created.status_code == 201, created.text
    env = created.json()
    assert env["agreement_id"] and env["document_sha256"]
    agreement = (await client.get(f"/agreements/{env['agreement_id']}", headers=admin)).json()
    assert agreement["kind"] == "nda" and agreement["status"] == "draft"
    wrong = await client.post("/envelopes", headers=admin, data={          # Ravi is C2C, not W-2
        "title": "Offer", "template": "offer_letter", "consultant_id": ravi, "signers": signer})
    assert wrong.status_code == 400, wrong.text
```
- [ ] **Step 2:** FAIL ("Attach the PDF to sign").
- [ ] **Step 3:** create `apps/api/app/services/esign_templates.py`:

```python
"""Built-in documents to send for signature: Mutual NDA, W-2 offer letter, 1099 contractor agreement.

The wording is a plain starting draft; each tenant's counsel should approve it before use."""

from __future__ import annotations

from datetime import date

from fpdf import FPDF

from .esign import _latin1

# key -> (agreement kind, tenant side, allowed engagements or None for any, title, paragraphs)
TEMPLATES: dict[str, tuple[str, str, tuple[str, ...] | None, str, list[str]]] = {
    "nda": ("nda", "employer", None, "Mutual Non-Disclosure Agreement", [
        "{tenant} and {person} agree to keep confidential all non-public business, technical and client information "
        "that either party shares with the other, including information belonging to {tenant}'s clients.",
        "Confidential information may be used only to perform the work for which it was shared and may be disclosed "
        "only to people who need it for that work and are bound by similar obligations.",
        "These obligations do not cover information that is public, already known, independently developed or "
        "lawfully received from someone else, or that the law requires to be disclosed.",
        "On request, or when the engagement ends, each party will return or destroy the other's confidential "
        "information. These obligations continue for two years after the engagement ends.",
    ]),
    "offer_letter": ("offer_letter", "employer", ("w2_contract", "w2_fulltime"), "Offer of Employment (W-2)", [
        "{tenant} is pleased to offer {person} employment as {role}, starting on or about {start}.",
        "This is a W-2 position. Pay, schedule and benefits are as discussed and confirmed in writing by {tenant}. "
        "Payroll taxes are withheld as required by law.",
        "Employment is at will and depends on completing Form I-9 employment eligibility verification, signing "
        "{tenant}'s confidentiality agreement and accepting its policies.",
    ]),
    "ica": ("ica", "buyer", ("1099",), "Independent Contractor Agreement (1099)", [
        "{person} will provide services to {tenant} as an independent contractor ({role}), beginning on or about {start}, "
        "as described in work orders issued under this agreement.",
        "{person} controls how the work is done, supplies their own tools, is responsible for their own taxes and "
        "insurance, and is not an employee of {tenant}. {tenant} will issue Form 1099-NEC as required.",
        "{tenant} pays approved hours at the rate in each work order, on the payment terms stated there. "
        "{person} keeps {tenant}'s and its clients' information confidential.",
        "Either party may end this agreement with written notice; work orders in progress end with it.",
    ]),
}


def render(key: str, *, tenant: str, person: str, role: str | None, start: date | None) -> bytes:
    kind, _, _, title, paragraphs = TEMPLATES[key]
    values = {"tenant": tenant, "person": person, "role": role or "consultant", "start": f"{start or date.today():%B %d, %Y}"}
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 10, _latin1(title))
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 6, _latin1(f"Between {tenant} and {person}. Date: {date.today():%B %d, %Y}."))
    for p in paragraphs:
        pdf.ln(3)
        pdf.multi_cell(0, 6, _latin1(p.format(**values)))
    pdf.ln(10)
    pdf.multi_cell(0, 6, _latin1(f"Signed electronically by both parties through myTrakIn ({kind.upper()})."))
    return bytes(pdf.output())
```
- [ ] **Step 4:** `routers/esign.py` `create_envelope`: add `template: str | None = Form(None, pattern="^(nda|offer_letter|ica)$")`;
  make the PDF block `if template: … elif file is not None: … elif document_path…: … else: raise`, template branch:

```python
    if template:
        kind, side, engagements, doc_title, _ = esign_templates.TEMPLATES[template]
        person = await db.one(
            """select c.full_name, c.engagement, c.title, (select min(p.start_date) from placements p where p.consultant_id = c.id) as start
                 from consultants c where c.id = :id""", {"id": consultant_id}) if consultant_id else None
        if person is None:
            raise bad_request("Pick the consultant this document is for")
        if engagements and person["engagement"] not in engagements:
            raise bad_request(f"{doc_title} is only for {' / '.join(engagements)} consultants")
        tenant = await db.val("select name from tenants where id = :t", {"t": db.ctx.tenant_id})
        data = esign_templates.render(template, tenant=tenant, person=person["full_name"], role=person["title"], start=person["start"])
        agreement_id = await db.val(
            """insert into agreements (tenant_id, code, kind, consultant_id, tenant_side, effective_on, status, source)
               values (:t, :code, :kind, :c, :side, current_date, 'draft', 'myTrakIn') returning id""",
            {"t": db.ctx.tenant_id, "code": f"{kind.upper().replace('_', '-')}-{str(consultant_id)[:8].upper()}-{date.today():%y%m%d}",
             "kind": kind, "c": consultant_id, "side": side})
```
  Imports: `from datetime import date`, `from ..services import esign_templates, storage`. Verify the consultants job
  title column name (`grep -n "create table consultants" -A 25 supabase/migrations/20261011000200_business.sql`).
- [ ] **Step 5: Web** (`esign/new/page.tsx`): `const [doc, setDoc] = useState(params.get("template") ?? "upload");`;
  select before the PDF field; show file input only when `doc === "upload"`:

```tsx
        <label htmlFor="d">Document</label>
        <select id="d" className="ctl" value={doc} onChange={(e) => setDoc(e.target.value)}>
          <option value="upload">Upload a PDF…</option>
          <option value="nda">Mutual NDA (template)</option>
          <option value="offer_letter">Offer letter — W-2 (template)</option>
          <option value="ica">Independent contractor agreement — 1099 (template)</option>
        </select>
        {doc !== "upload" && !params.get("consultant_id") && <p className="err">Open this from the consultant's page so the template is filled in for them.</p>}
```
  `submit`: `if (doc === "upload" && !file) return alert(...)`; `if (doc !== "upload") form.set("template", doc);`; only
  upload/set file when `doc === "upload"`. On `consultants/[id]/page.tsx` add links
  `/esign/new?consultant_id=${id}&template=<t>&title=…` for the templates allowed for that engagement.
- [ ] **Step 6:** CI + typecheck; open one generated PDF to eyeball. **Step 7:** commit `feat(esign): ESG-02 NDA, W-2 offer, 1099 ICA templates`.

---

### Task 10: Docs, status, verification (Definition of Done)

- [ ] PLAN.md: AGR-04/05/09 ✅, PRJ-03 ✅, TS-04/06 ✅, TS-07 ✅ (invoiced weeks → credit note, Phase 1), TS-10 🟡
  (client-approver e-mail field needed), ESG-02 ✅ (wording pending counsel → §6 decision). §9 progress line.
- [ ] CHANGELOG entry; regenerate `docs/api-reference.md` (Makefile `api-docs` target) for `/timesheets/remind`,
  `/agreements/{id}/renew`, `/placements?project_id`, `template` on `/envelopes`.
- [ ] Verify: CI green; `npm run typecheck` + `npm run build`; click through as admin, finance, vendor, consultant
  (phone width + dark mode).
- [ ] Update memory `project-plan-and-gaps.md`; commit `docs: PLAN/CHANGELOG for AGR/PRJ/TS/ESG gaps`; ask before push/merge.

## Out of scope (named so nothing is "missed")

- Credit notes / correction lines for invoiced adjustments → PLAN Phase 1.
- Client-approver notification on time off → needs approver e-mail on projects.
- Template-version / countersigner signing limit (spec §6.6 superseded form) → separate ESG item.
- ACC-03 account-manager scoping → its own PLAN item.
