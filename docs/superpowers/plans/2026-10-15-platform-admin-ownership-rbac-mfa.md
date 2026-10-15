# Platform admin, company activation, ownership, roles & permissions, per-user MFA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Any signed-in user can create a company; the platform admin reviews and activates it; the creator becomes its owner and can transfer ownership; the owner builds fully custom roles and per-user permissions (none / view / edit per module); every user the owner allows can switch two-step verification on or off; the platform admin gets a dashboard of platform-wide analytics.

**Architecture:** There is no "workspace" in the product any more. Internally every table is isolated by `tenant_id` + RLS. That plumbing stays, invisible: **one company = one tenant**. Creating a company opens a new tenant (status `onboarding`) with the creator as its owner. Until the platform admin activates it, the company can only finish onboarding. Permissions are a layer *on top of* the existing base roles: the base role still decides row scope and amount masking (RULE-01/02). A custom role or per-user override can narrow any module to view-only or hidden. It is enforced once, centrally, in `tenant_db`, by mapping URL prefix → module and HTTP method → read/write. Platform analytics come from `security definer` SQL functions that return **aggregates only**.

**Tech Stack:** FastAPI + raw SQL (`app/db.py` `Db` helpers), Postgres/Supabase migrations with RLS, pytest (`httpx.ASGITransport`, fixtures in `apps/api/tests/conftest.py`), Next.js 16 App Router (`apps/web`), no new dependencies.

---

## 0. Decisions this plan is built on (owner, 2026-10-15)

| # | Decision |
|---|---|
| D-P1 | No workspaces. A user creates a **company**; the **platform admin activates** it; the creator is its **owner**. |
| D-P2 | Owner can **transfer ownership** to another active staff user. Exactly one owner per company. |
| D-P3 | Owner configures **roles & permissions** with full customisation: custom roles (for example "Finance – view only") and per-user overrides (F1 finance read-only, F2 finance read+write). |
| D-P4 | MFA is **the user's choice**: the owner allocates the MFA option per user; allocated users turn it on or off themselves. **Nobody is forced**, finance and admins included. This replaces `REQUIRE_MFA_FOR_MONEY_ROLES`. |
| D-P5 | Platform analytics = SaaS revenue (MRR/ARR) **plus money moving through the platform** (invoiced / collected / AP paid), **aggregates only**. |
| D-P6 | **RULE-05 is amended**: the platform admin may see the onboarding record (company details, W-9 fields + file, verification checks) of a company **awaiting activation**, and per-company money **totals**. Nothing else in a company. |

**Assumptions (correct them before Phase A starts if wrong):**
- **A1.** Client / vendor / end-client *records* that a company adds for its own business are not platform accounts. They are still activated by that company's own staff, as today. Only a company that registers to *use* myTrakIn needs platform activation.
- **A2.** The public `/signup` request form and the platform "Create workspace" button are **removed**; registering through the company wizard replaces them. The `tenant_signups` table is kept (history) but nothing writes to it.
- **A3.** The 30-day trial starts on activation, not on registration.
- **A4.** MFA option defaults to **allowed** for every existing and new user (`memberships.mfa_allowed default true`).
- **A5.** v1 permissions can only **narrow** what a base role already allows. Granting *more* than the base role (for example an account manager editing invoices) needs every hard-coded role check (~120 in the API, 69 `can()` calls in RLS) rewritten. That is ~5× this plan, so it is follow-up **P-12** rather than done here.

## 1. File map

| File | Change | Responsibility |
|---|---|---|
| `supabase/migrations/20261016000100_company_accounts.sql` | create | tenant owner/company link, `start_company_account()`, `purge_abandoned_accounts()`, `is_account_owner()` |
| `supabase/migrations/20261016000200_roles_permissions.sql` | create | `custom_roles`, `memberships.custom_role_id/permission_overrides`, RLS |
| `supabase/migrations/20261016000300_user_mfa.sql` | create | `memberships.mfa_allowed`, `user_has_mfa()`, `mfa_allowed_for()` |
| `supabase/migrations/20261016000400_platform_analytics.sql` | create | `platform_companies()`, `platform_money_stats()`, `platform_money_trend()`, `platform_overview()` |
| `apps/api/app/permissions.py` | create | module catalogue, `effective()`, `required()`, `check()` (pure, unit-tested) |
| `apps/api/app/deps.py` | modify | owner/status/permissions/MFA in `tenant_db`; pending-activation, permission and MFA gates; drop money-role MFA |
| `apps/api/app/config.py` | modify | delete `require_mfa_for_money_roles` |
| `apps/api/app/routers/onboarding.py` | modify | `POST /onboarding/accounts`; `complete` links company ↔ account |
| `apps/api/app/routers/companies.py` | modify | own company record can't be self-activated |
| `apps/api/app/routers/admin.py` | modify | transfer ownership; owner protected; `mfa_allowed`; MFA column in users list |
| `apps/api/app/routers/roles.py` | create | custom roles CRUD + per-user access (owner only) |
| `apps/api/app/routers/me.py` | modify | `/session` → `is_owner`, `permissions`; `/me` → `mfa_allowed` |
| `apps/api/app/routers/platform.py` | modify | activation queue + decision, platform admins, owner rescue, analytics; remove create-tenant + signups |
| `apps/api/app/routers/public.py` | modify | remove `POST /public/signups` |
| `apps/api/app/routers/cron.py` | modify | purge abandoned draft companies |
| `apps/api/app/main.py` | modify | register `roles` router |
| `apps/api/tests/test_permissions_unit.py` | create | unit tests for `permissions.py` (`--noconftest`) |
| `apps/api/tests/test_company_accounts.py` | create | create → pending → activate → owner → transfer; platform admins |
| `apps/api/tests/test_roles.py` | create | F1 read-only vs F2 read/write; owner only; validation |
| `apps/api/tests/test_mfa_choice.py` | create | not forced; on → aal2 needed; allocation |
| `apps/api/tests/test_platform_analytics.py` | create | metrics shape, aggregates only, admin only |
| `apps/api/tests/conftest.py` | modify | `founder` + `finance2` users; `auth.mfa_factors` stub |
| `apps/api/tests/test_access.py`, `test_flows.py` | modify | replace money-role MFA test and signup-approval test |
| `apps/web/src/components/AppShell.tsx` | modify | "Create your company", "Waiting for activation", nav hides hidden modules, MFA text |
| `apps/web/src/lib/session.tsx` | modify | `perm()`, `canEdit()`, `isOwner()` |
| `apps/web/src/app/(app)/settings/roles/page.tsx` | create | Roles & permissions editor (owner) |
| `apps/web/src/app/(app)/users/page.tsx` | modify | access editor, MFA option, Transfer ownership, owner badge |
| `apps/web/src/app/(app)/account/page.tsx` | modify | MFA on/off governed by `mfa_allowed` |
| `apps/web/src/app/(app)/platform/page.tsx` | modify | Overview dashboard, Companies, Activation queue, Platform admins |
| `apps/web/src/app/signup/page.tsx` | modify | redirect to `/create-account` |
| UI copy in ~30 files | modify | "workspace" → "company" (user-visible text only) |
| `docs/PLAN.md`, `CHANGELOG.md`, `docs/security.md`, `docs/functional.md`, `docs/technical.md` | modify | Phase P section, RULE-05 amendment, MFA change |

**Order** (riskiest first, each phase shippable): **A** company accounts → **B** platform activation → **C** ownership → **D** roles & permissions → **E** MFA → **F** analytics → **G** wording, docs, verification.

Production DB has no `supabase_migrations` table; migrations are applied by hand. **Never apply to prod without the owner's go-ahead.**

---

## Phase A — A company is its own account

### Task A1: Migration — company account, owner, creation

**Files:** Create `supabase/migrations/20261016000100_company_accounts.sql`

- [ ] **Step 1: Write the migration**

```sql
-- =============================================================================
-- myTrakIn · P · 0100 · One company = one account (tenant). No workspaces in the product.
--   tenants.owner_membership_id  exactly one owner per company (transferable)
--   tenants.company_id           the company's own profile record (W-9, domain, members)
--   tenants.activated_*          platform activation (status onboarding → active)
--   start_company_account()      any signed-in user opens a new company (pending activation)
--   purge_abandoned_accounts()   drafts never finished within 7 days are removed
-- =============================================================================
set search_path = mytrakin, public, extensions;

alter table tenants
  add column if not exists owner_membership_id uuid references memberships (id) on delete set null,
  add column if not exists company_id          uuid references companies (id) on delete set null,
  add column if not exists activated_at        timestamptz,
  add column if not exists activated_by        uuid,
  add column if not exists decision_note       text;

-- Existing companies: the earliest active admin is the owner.
update tenants t
   set owner_membership_id = (select m.id from memberships m
                               where m.tenant_id = t.id and m.role = 'tenant_admin' and m.status = 'active'
                               order by m.created_at limit 1)
 where owner_membership_id is null;
update tenants set activated_at = created_at where status = 'active' and activated_at is null;

-- Is the caller the owner of the current company?
create or replace function is_account_owner() returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select exists (select 1 from tenants t join memberships m on m.id = t.owner_membership_id
                  where t.id = ctx_tenant() and m.user_id = ctx_user() and m.status = 'active')
$$;

-- Opens a new company for a signed-in user. Runs before any tenant context exists,
-- hence security definer. At most 3 unfinished/pending companies per person.
create or replace function start_company_account(p_user uuid) returns uuid
language plpgsql security definer set search_path = mytrakin, public, extensions as $$
declare t uuid; m uuid; pending int;
begin
  select count(*) into pending
    from tenants tt join memberships mm on mm.id = tt.owner_membership_id
   where mm.user_id = p_user and tt.status = 'onboarding';
  if pending >= 3 then
    raise exception 'too_many_pending' using errcode = 'P0001';
  end if;
  insert into tenants (name, status) values ('New company', 'onboarding') returning id into t;
  insert into memberships (tenant_id, user_id, role, title, status)
       values (t, p_user, 'tenant_admin', 'Owner', 'active') returning id into m;
  update tenants set owner_membership_id = m where id = t;
  perform seed_tenant_defaults(t);
  return t;
end $$;

create or replace function purge_abandoned_accounts() returns int
language sql security definer set search_path = mytrakin, public, extensions as $$
  with gone as (delete from tenants where status = 'onboarding' and company_id is null
                                      and created_at < now() - interval '7 days' returning 1)
  select count(*)::int from gone
$$;

revoke all on function is_account_owner(), start_company_account(uuid), purge_abandoned_accounts() from public;
grant execute on function is_account_owner(), start_company_account(uuid), purge_abandoned_accounts() to mytrakin_api;
```

- [ ] **Step 2: Apply locally.** Run `make test` (the session fixture rebuilds the DB from every migration). Expected: no migration error; the same pass/fail count as before. The 2 team W-9 tests that already fail on main are known.
- [ ] **Step 3: Commit** `feat(P-01): one company = one account — owner + activation columns, start_company_account()`

### Task A2: Test users

**Files:** Modify `apps/api/tests/conftest.py:42-49`

- [ ] Add `"founder": "founder@newco.example"` (brand-new user) and `"finance2": "finance2@example.com"` (second finance user for Phase D) to `USERS`. `finance2` gets its membership inside its own test.

### Task A3: `POST /onboarding/accounts` + pending-activation gate

**Files:** Modify `apps/api/app/routers/onboarding.py`, `apps/api/app/deps.py`, `apps/api/app/routers/companies.py`, `apps/api/app/routers/me.py`; Test `apps/api/tests/test_company_accounts.py`

- [ ] **Step 1: Failing test**

```python
"""One company = one account: create → pending activation → platform activates → owner."""
from __future__ import annotations

from tests.test_company_onboarding import w9_pdf


async def _founder_company(client, auth, n: int, ein: str) -> dict:
    """Founder (no company yet) runs the full US wizard. Returns {tenant_id, company_id, headers, ...}."""
    h = auth("founder")
    started = await client.post("/onboarding/accounts", headers=h, json={"country": "US"})
    assert started.status_code == 201, started.text
    tid, sid = started.json()["tenant_id"], started.json()["id"]
    h = {**h, "X-Tenant-Id": tid}
    up = await client.post(f"/onboarding/sessions/{sid}/w9", headers=h,
                           files={"file": ("w9.pdf", w9_pdf(ein, f"Founder {n} Staffing LLC"), "application/pdf")})
    assert up.status_code == 200, up.text
    d = await client.patch(f"/onboarding/sessions/{sid}", headers=h, json={
        "kind": "vendor", "domain": f"founder{n}.example", "company_email": f"ops@founder{n}.example", "ein": ein})
    assert d.status_code == 200, d.text
    code = (await client.post(f"/onboarding/sessions/{sid}/email-code", headers=h, json={})).json()
    assert (await client.post(f"/onboarding/sessions/{sid}/email-verify", headers=h,
                              json={"code": code["test_code"]})).status_code == 200
    done = await client.post(f"/onboarding/sessions/{sid}/complete", headers=h, json={"authorized": True})
    assert done.status_code == 201, done.text
    return {**done.json(), "tenant_id": tid, "headers": h}


async def test_new_user_creates_company_pending_activation(client, auth):
    acct = await _founder_company(client, auth, 1, "31-4159261")
    h = acct["headers"]
    s = (await client.get("/session", headers=h)).json()
    assert s["role"] == "tenant_admin" and s["is_owner"] is True
    assert s["tenant"]["status"] == "onboarding" and s["tenant"]["name"] == "Founder 1 Staffing LLC"
    blocked = await client.get("/invoices", headers=h)
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "pending_activation"
    assert (await client.get(f"/companies/{acct['company_id']}", headers=h)).status_code == 200
    own = await client.post(f"/companies/{acct['company_id']}/activate", headers=h)
    assert own.status_code == 403            # only the platform activates the company's own record


async def test_pending_company_limit(client, auth):
    h = auth("founder")
    for _ in range(3):
        await client.post("/onboarding/accounts", headers=h, json={"country": "US"})
    r = await client.post("/onboarding/accounts", headers=h, json={"country": "US"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_pending"
```

Test order matters: run `test_pending_company_limit` **last** in this file (put it at the bottom). It leaves the founder at the limit, so the later founder tests must run before it. Alternatively, clean up in a `finally:` with `delete from mytrakin.tenants where company_id is null and status='onboarding' and name='New company'`. Prefer the cleanup.

- [ ] **Step 2: Run** `cd apps/api && .venv/Scripts/pytest tests/test_company_accounts.py -v` → FAIL (404 on `/onboarding/accounts`).

- [ ] **Step 3: Endpoint** (onboarding.py, next to `start_session` at :128)

```python
from sqlalchemy.exc import DBAPIError

from ..deps import user_db


@router.post("/accounts", status_code=201)
async def start_account(body: SessionIn, db: TenantDb = Depends(user_db)):
    """Create my company: opens a new company (pending platform activation) with me as its
    owner and starts the wizard inside it. The web app then sends X-Tenant-Id = tenant_id."""
    try:
        async with db.conn.begin_nested():
            tid = await db.val("select mytrakin.start_company_account(:u)", {"u": db.ctx.user_id})
    except DBAPIError as exc:
        if "too_many_pending" in str(exc):
            raise ApiError(429, "too_many_pending",
                           "You already have 3 companies waiting — finish or wait for those first") from exc
        raise
    await db.run("select mytrakin.begin_request(:u, :t, 'tenant_admin', null, null, :ip, :ua)",
                 {"u": db.ctx.user_id, "t": tid, "ip": db.ctx.ip, "ua": db.ctx.user_agent})
    db.ctx.tenant_id = tid
    row = await db.one("insert into onboarding_sessions (tenant_id, country, created_by) values (:t, :c, :u) returning *",
                       {"t": tid, "c": body.country, "u": db.ctx.user_id})
    return {**_public_session(row), "tenant_id": tid}
```

- [ ] **Step 4: Link company ↔ account** — at the end of `complete_onboarding`, after `update onboarding_sessions …`:

```python
    # Registering my own company (an account still waiting for its profile): link it and name the account.
    await db.run(
        """update tenants set company_id = :c, name = :n, ein = :ein, state = :s
            where id = :t and company_id is null and status = 'onboarding'""",
        {"c": company["id"], "n": cols["name"], "ein": cols["ein"], "s": cols["state"], "t": db.ctx.tenant_id})
```

Counterparty records added by staff of an **active** company don't match `status = 'onboarding'`, so nothing changes for them.

- [ ] **Step 5: Gate in `deps.py`** (helpers extended in C1, D3, E2):

```python
# Paths a company may use while it waits for platform activation.
PENDING_OK = ("/v1/session", "/v1/companies", "/v1/onboarding")


async def _account_state(conn, ctx: Ctx) -> dict:
    """Company status + whether the caller owns it (one round trip; permissions join in at D3)."""
    return (await conn.execute(text(
        """select t.status, t.owner_membership_id = cast(:m as uuid) as is_owner
             from mytrakin.tenants t where t.id = :t"""), {"t": ctx.tenant_id, "m": ctx.membership_id})).mappings().first()


def _gate(request: Request, state) -> None:
    if state["status"] == "onboarding" and not request.url.path.startswith(PENDING_OK):
        raise ApiError(403, "pending_activation",
                       "Your company is waiting for activation by the myTrakIn team. You can finish your company profile meanwhile.")
```

In `tenant_db`, after `ctx` is built:

```python
        state = await _account_state(conn, ctx)
        ctx.is_owner = bool(state["is_owner"])
        _gate(request, state)
```

Add `is_owner: bool = False` to `Ctx`.

- [ ] **Step 6: Own record can't be self-activated** — `companies.activate_company`, right after `_company_or_404`:

```python
    if await db.val("select 1 from tenants where id = :t and company_id = :c", {"t": db.ctx.tenant_id, "c": company_id}):
        raise forbidden("Your own company is activated by the myTrakIn platform team")
```

- [ ] **Step 7: `/session`** — select `id, name, plan, status, company_id` from tenants (the tenant's own company id, used by the waiting screen) and add `"is_owner": ctx.is_owner`.
- [ ] **Step 8: Run** `pytest tests/test_company_accounts.py tests/test_company_onboarding.py tests/test_access.py -v` → new tests PASS; existing onboarding tests still pass (they run inside the active demo company).
- [ ] **Step 9: Commit** `feat(P-01): any user creates a company account; pending-activation gate`

### Task A4: Remove the old sign-up request and "Create workspace"

- [ ] Delete `POST /public/signups` (public.py:366 onwards + unused models/imports). In platform.py, delete `TenantIn`, `create_tenant`, `_open_workspace`, `signups`, `SignupDecision`, `decide_signup`. Delete `test_signup_and_platform_approval` (test_flows.py:198; B1 replaces it). `apps/web/src/app/signup/page.tsx` → `redirect("/create-account")` from `next/navigation`.
- [ ] `grep -rn "signups\|create_tenant\|_open_workspace" apps/api/app apps/web/src` → nothing left except migrations.
- [ ] `pytest -q` → no import errors. Commit `refactor(P-11): drop sign-up requests and Create workspace — the company wizard replaces both`

### Task A5: Web — "Create your company" and the waiting screen

- [ ] Find the wizard start: `grep -rn "onboarding/sessions\"" apps/web/src`. For a user with **no company** (`noWorkspace`, AppShell.tsx:77), call `POST /onboarding/accounts` instead. Then select the returned `tenant_id` with the same setter the company switcher uses (`grep -n "x-tenant-id" apps/web/src/lib/api.ts` shows where the header value comes from). The rest of the wizard is unchanged.
- [ ] AppShell no-company screen: heading "Create your company", one primary button that opens the wizard. Remove the "ask your administrator" copy.
- [ ] Where AppShell handles `mfa_required` (AppShell.tsx:103), add `pending_activation`:

```tsx
<h2>Waiting for activation</h2>
<p className="muted">The myTrakIn team is reviewing {ws.tenant.name}. We'll e-mail you as soon as it's active. You can still complete your company profile.</p>
<p><Link className="btn" href={`/companies/${ws.tenant.company_id ?? ""}`}>Open company profile</Link></p>
```

- [ ] `cd apps/web && npx tsc --noEmit && npm run lint` → clean. Commit `feat(P-01): web — create your company, waiting-for-activation screen`

---

## Phase B — Platform admin activates companies

### Task B1: Activation queue + decision

**Files:** platform.py; create `supabase/migrations/20261016000400_platform_analytics.sql` (extended in F1); Test `test_company_accounts.py`

- [ ] **Step 1: Failing test**

```python
async def test_platform_activates_company_and_owner_gets_in(client, auth):
    acct = await _founder_company(client, auth, 2, "27-1828182")
    p = auth("platform")
    assert (await client.get("/platform/companies?status=pending", headers=auth("admin"))).status_code == 403
    queue = (await client.get("/platform/companies?status=pending", headers=p)).json()
    row = next(r for r in queue if r["tenant_id"] == acct["tenant_id"])
    assert row["name"] == "Founder 2 Staffing LLC" and row["owner_email"] == "founder@newco.example"
    detail = (await client.get(f"/platform/companies/{acct['tenant_id']}", headers=p)).json()
    assert detail["company"]["w9_status"] == "submitted" and "checks" in detail
    no_note = await client.post(f"/platform/companies/{acct['tenant_id']}/decision", headers=p, json={"decision": "needs_info"})
    assert no_note.status_code == 400
    ok = await client.post(f"/platform/companies/{acct['tenant_id']}/decision", headers=p, json={"decision": "activate"})
    assert ok.status_code == 200, ok.text
    h = acct["headers"]
    assert (await client.get("/session", headers=h)).json()["tenant"]["status"] == "active"
    assert (await client.get("/invoices", headers=h)).status_code == 200
    assert (await client.get(f"/companies/{acct['company_id']}", headers=h)).json()["status"] == "active"
```

- [ ] **Step 2: Run** → FAIL (404).
- [ ] **Step 3: SQL** (new file `20261016000400_platform_analytics.sql`)

```sql
-- =============================================================================
-- myTrakIn · P · 0400 · Platform admin: company list/queue and analytics. Aggregates only
-- (RULE-05 as amended 2026-10-15). Every function returns nothing unless the caller is platform admin.
-- =============================================================================
set search_path = mytrakin, public, extensions;

create or replace function platform_companies()
returns table (tenant_id uuid, company_id uuid, name text, kind text, country text, state text, domain text,
               status text, plan text, created_at timestamptz, activated_at timestamptz, decision_note text,
               owner_name text, owner_email text, w9_status text, onboarding_stage smallint)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select t.id, c.id, coalesce(c.name, t.name), c.kind, c.country, coalesce(c.state, t.state), c.domain,
         t.status, t.plan, t.created_at, t.activated_at, t.decision_note,
         p.full_name, coalesce(p.email, m.invited_email::text), c.w9_status, c.onboarding_stage
    from tenants t
    left join companies c on c.id = t.company_id
    left join memberships m on m.id = t.owner_membership_id
    left join profiles p on p.id = m.user_id
   where is_platform_admin()
$$;
revoke all on function platform_companies() from public;
grant execute on function platform_companies() to mytrakin_api;
```

Check `companies.onboarding_stage`'s type (`grep -n "onboarding_stage" supabase/migrations/20261011000700_company_onboarding.sql`); if it isn't `smallint`, match it in the `returns table`.

- [ ] **Step 4: Endpoints** (platform.py)

```python
from . import companies as companies_router


async def _enter(db: TenantDb, tenant_id: UUID) -> None:
    """Act inside one company as 'system' for a platform action (audited with the platform user's id)."""
    await db.run("select mytrakin.begin_request(:u, :t, 'system', null, null, :ip, :ua)",
                 {"u": db.ctx.user_id, "t": tenant_id, "ip": db.ctx.ip, "ua": db.ctx.user_agent})


async def _leave(db: TenantDb) -> None:
    await db.run("select mytrakin.begin_request(:u, null, 'platform_admin', null, null, :ip, :ua)",
                 {"u": db.ctx.user_id, "ip": db.ctx.ip, "ua": db.ctx.user_agent})


@router.get("/companies")
async def companies(db: TenantDb = Depends(platform_db), status: str | None = None):
    """Every company on myTrakIn. status=pending → registered and waiting for activation."""
    rows = await db.all("select * from mytrakin.platform_companies() order by created_at desc")
    if status == "pending":
        return [r for r in rows if r["status"] == "onboarding" and r["company_id"] is not None]
    return [r for r in rows if status is None or r["status"] == status]


@router.get("/companies/{tenant_id}")
async def company_review(tenant_id: UUID, db: TenantDb = Depends(platform_db)):
    """What the platform needs to decide: the company's onboarding record, W-9 and verification checks."""
    tenant = await db.one("select * from tenants where id = :id", {"id": tenant_id})
    if tenant is None or tenant["company_id"] is None:
        raise not_found("Company")
    await _enter(db, tenant_id)
    company = await companies_router._company_or_404(db, tenant["company_id"])
    checks = await companies_router._run_verification(db, company)
    await _leave(db)
    keep = ("id", "business_code", "name", "kind", "country", "state", "address", "domain", "dba", "business_type",
            "contact_name", "contact_email", "tin", "cin", "tax_classification", "tax_address", "w9_data",
            "w9_status", "w9_document_id", "status", "created_at")
    return {"tenant": tenant, "company": {k: company.get(k) for k in keep}, **checks}


class CompanyDecision(BaseModel):
    decision: str = Field(pattern="^(activate|needs_info|reject)$")
    note: str | None = Field(None, max_length=1000)


@router.post("/companies/{tenant_id}/decision")
async def decide_company(tenant_id: UUID, body: CompanyDecision, db: TenantDb = Depends(platform_db)):
    tenant = await db.one("select * from tenants where id = :id for update", {"id": tenant_id})
    if tenant is None or tenant["company_id"] is None:
        raise not_found("Company")
    if tenant["status"] != "onboarding":
        raise conflict(f"This company is already {tenant['status']}")
    if body.decision != "activate" and not body.note:
        raise bad_request("Add a note so the owner knows why")
    owner = await db.one(
        """select coalesce(p.email, m.invited_email::text) as email from memberships m
             left join profiles p on p.id = m.user_id where m.id = :m""", {"m": tenant["owner_membership_id"]})
    if body.decision == "activate":
        await _enter(db, tenant_id)
        # The platform reviewed the W-9 on the review screen: that is the staff verification.
        await db.run("""update companies set w9_status = 'verified', w9_decided_at = now(), w9_decided_by = :u
                         where id = :c and w9_status in ('submitted', 'under_review')""",
                     {"u": db.ctx.user_id, "c": tenant["company_id"]})
        company = await companies_router._company_or_404(db, tenant["company_id"])
        result = await companies_router._run_verification(db, company)
        if result["blockers"]:
            raise ApiError(422, "verification_failed", "Can't activate yet: " + "; ".join(result["blockers"]))
        await db.run("update companies set status = 'active', onboarding_stage = 8, verified_at = now() where id = :c",
                     {"c": tenant["company_id"]})
        await _leave(db)
    new_status = {"activate": "active", "needs_info": "onboarding", "reject": "closed"}[body.decision]
    await db.run(
        """update tenants set status = :s, decision_note = :n,
                  activated_at = case when :s = 'active' then now() end,
                  activated_by = case when :s = 'active' then cast(:u as uuid) end,
                  trial_ends_on = case when :s = 'active' then current_date + :trial else trial_ends_on end
            where id = :id""",
        {"s": new_status, "n": body.note, "u": db.ctx.user_id, "trial": TRIAL_DAYS, "id": tenant_id})
    if owner and owner["email"]:
        login = f"{get_settings().web_origin.rstrip('/')}/login?email={owner['email']}"
        lines = {"activate": [f"{tenant['name']} is now active on myTrakIn. Your 30-day trial starts today."],
                 "needs_info": ["We need a little more before we can activate your company:", body.note or ""],
                 "reject": ["We're not able to activate this company on myTrakIn.", body.note or ""]}[body.decision]
        await send_email(None, to=owner["email"], subject=f"{tenant['name']} on myTrakIn", kind="welcome",
                         html_body=render(f"About {tenant['name']}", lines, button=("Open myTrakIn", login)))
    return {"tenant_id": tenant_id, "status": new_status}
```

The existing `audit_row` triggers on `tenants` and `companies` log every write, with `actor_id` = the platform user. Import `ApiError` from `..errors`.

- [ ] **Step 5:** Run B1 + `test_access.py` → PASS. **Commit** `feat(P-02): platform admin reviews and activates companies`

### Task B2: Platform admins manage platform admins

- [ ] **Step 1: Failing test** (in `test_company_accounts.py`)

```python
async def test_platform_admins_managed_by_platform_only(client, auth):
    p = auth("platform")
    assert (await client.get("/platform/admins", headers=auth("admin"))).status_code == 403
    assert (await client.post("/platform/admins", headers=p, json={"email": "admin@example.com"})).status_code == 201
    rows = (await client.get("/platform/admins", headers=p)).json()
    me = next(a for a in rows if a["email"] == "owner@mytrakin.example")
    other = next(a for a in rows if a["email"] == "admin@example.com")
    assert (await client.delete(f"/platform/admins/{me['user_id']}", headers=p)).status_code == 400   # not yourself
    assert (await client.delete(f"/platform/admins/{other['user_id']}", headers=p)).status_code == 200
```

- [ ] **Step 2: Implement**

```python
@router.get("/admins")
async def admins(db: TenantDb = Depends(platform_db)):
    return await db.all("""select pa.user_id, p.email, p.full_name from platform_admins pa
                             join profiles p on p.id = pa.user_id order by p.email""")


class AdminIn(BaseModel):
    email: EmailStr


@router.post("/admins", status_code=201)
async def add_admin(body: AdminIn, db: TenantDb = Depends(platform_db)):
    uid = await db.val("select id from profiles where email = :e", {"e": body.email})
    if uid is None:
        raise bad_request("This person has to sign in to myTrakIn once before they can be made a platform admin")
    await db.run("insert into platform_admins (user_id) values (:u) on conflict do nothing", {"u": uid})
    return {"user_id": uid, "email": body.email}


@router.delete("/admins/{user_id}")
async def remove_admin(user_id: UUID, db: TenantDb = Depends(platform_db)):
    if user_id == db.ctx.user_id:
        raise bad_request("You can't remove yourself — ask another platform admin")
    if await db.run("delete from platform_admins where user_id = :u", {"u": user_id}) == 0:
        raise not_found("Platform admin")
    return {"user_id": user_id, "removed": True}
```

Check the `platform_admins` policies (`grep -n "on platform_admins" supabase/migrations/*.sql`; security.sql:110 shows a select policy). If no write policy exists, append to migration 0400:

```sql
drop policy if exists platform_admins_manage on platform_admins;
create policy platform_admins_manage on platform_admins for all to mytrakin_api
  using (is_platform_admin()) with check (is_platform_admin());
grant insert, delete on platform_admins to mytrakin_api;
```

- [ ] **Step 3:** PASS → commit `feat(P-03): platform admins manage platform admins`

### Task B3: Web — Activation queue + Platform admins tabs

- [ ] platform/page.tsx: tabs become `overview | companies | queue | admins` (overview is built in F3). Remove "Create workspace" (button, `Modal`) and the sign-up tab and `Drawer`.
- [ ] `queue`: `DataTable id="platform-queue"` over `GET /platform/companies?status=pending`, with columns Company, Owner, Owner e-mail, Country, Kind, Registered. Row → `Drawer` loading `GET /platform/companies/{tenant_id}`: company and W-9 fields (`<dl>`), a "View W-9" link (reuse the document-link call in `companies/[id]/page.tsx`; `grep -n "w9_document_id"` there), checks as `Chip`s, and the buttons **Activate** (pri), **Ask for more info**, **Reject**. The last two need a note `textarea` and stay disabled until it has text.
- [ ] `admins`: list + "Add platform admin" (e-mail) + Remove (hidden on your own row).
- [ ] tsc + lint; manual check as `owner@mytrakin.example`. Commit `feat(P-02): web — activation queue and platform admins`

---

## Phase C — Owner and transfer of ownership

### Task C1: Transfer ownership; the owner can't be demoted

- [ ] **Step 1: Failing test** (`test_company_accounts.py`)

```python
async def test_owner_transfers_ownership(client, auth, user_ids):
    from sqlalchemy import text

    from app.db import get_engine
    acct = await _founder_company(client, auth, 3, "45-9045090")
    await client.post(f"/platform/companies/{acct['tenant_id']}/decision", headers=auth("platform"), json={"decision": "activate"})
    h = acct["headers"]
    async with get_engine().begin() as conn:                         # 'outsider' joins as finance
        mid = (await conn.execute(text(
            """insert into mytrakin.memberships (tenant_id, user_id, role, status)
               values (:t, :u, 'finance', 'active') returning id"""),
            {"t": acct["tenant_id"], "u": user_ids["outsider"]})).scalar()
    me = (await client.get("/session", headers=h)).json()["membership_id"]
    assert (await client.patch(f"/users/{me}", headers=h, json={"role": "finance"})).status_code == 400
    oh = {**auth("outsider"), "X-Tenant-Id": acct["tenant_id"]}
    assert (await client.post(f"/users/{me}/transfer-ownership", headers=oh)).status_code == 403
    moved = await client.post(f"/users/{mid}/transfer-ownership", headers=h)
    assert moved.status_code == 200, moved.text
    s_new, s_old = (await client.get("/session", headers=oh)).json(), (await client.get("/session", headers=h)).json()
    assert s_new["is_owner"] is True and s_new["role"] == "tenant_admin" and s_old["is_owner"] is False
```

- [ ] **Step 2: Implement** (admin.py; import `INTERNAL_ROLES` from `..deps`)

```python
@router.post("/users/{membership_id}/transfer-ownership")
async def transfer_ownership(membership_id: UUID, db: TenantDb = Depends(tenant_db)):
    """Hand the company to another staff user. They become admin + owner; you stay an admin."""
    if not db.ctx.is_owner:
        raise forbidden("Only the company owner can transfer ownership")
    target = await db.one("select id, user_id, role, status from memberships where id = :id", {"id": membership_id})
    if target is None:
        raise not_found("User")
    if target["id"] == db.ctx.membership_id:
        raise bad_request("You already own this company")
    if target["status"] != "active" or target["user_id"] is None:
        raise bad_request("Ownership can only go to an active user who has signed in at least once")
    if target["role"] not in INTERNAL_ROLES:
        raise bad_request("Ownership can only go to a staff user — not a vendor, client or consultant login")
    await db.run("update memberships set role = 'tenant_admin' where id = :id", {"id": membership_id})
    tenant = await db.one("update tenants set owner_membership_id = :m where id = :t returning name, company_id",
                          {"m": membership_id, "t": db.ctx.tenant_id})
    if tenant["company_id"]:
        # keep the company profile's top role in step with the owner
        await db.run("update company_members set company_role = 'admin' where company_id = :c and company_role = 'super_admin'",
                     {"c": tenant["company_id"]})
        if await db.run("""update company_members set company_role = 'super_admin', status = 'active'
                            where company_id = :c and user_id = :u""",
                        {"c": tenant["company_id"], "u": target["user_id"]}) == 0:
            await db.run("""insert into company_members (tenant_id, company_id, user_id, company_role, status)
                            values (:t, :c, :u, 'super_admin', 'active')""",
                         {"t": db.ctx.tenant_id, "c": tenant["company_id"], "u": target["user_id"]})
    new_email = await db.val("select email from profiles where id = :u", {"u": target["user_id"]})
    for to, line in ((new_email, f"You are now the owner of {tenant['name']} on myTrakIn."),
                     (db.ctx.email, f"You transferred ownership of {tenant['name']} to {new_email}. You remain an admin.")):
        if to:
            await send_email(db, to=to, subject=f"Ownership of {tenant['name']}", kind="welcome",
                             tenant_id=db.ctx.tenant_id, html_body=render("Company ownership changed", [line]))
    return {"owner_membership_id": membership_id}
```

- [ ] **Step 3: Protect the owner** — in `update_user` (after `target` is loaded) and `cancel_invite`:

```python
    owner = await db.val("select owner_membership_id from tenants where id = :t", {"t": db.ctx.tenant_id})
    if membership_id == owner and (fields.get("role", "tenant_admin") != "tenant_admin"
                                   or fields.get("status", "active") != "active"):
        raise bad_request("This is the company owner — transfer ownership first")
```

(`cancel_invite`: `if membership_id == owner: raise bad_request(...)`.)

- [ ] **Step 4: Owner rescue** (platform.py), for when an owner leaves:

```python
class OwnerIn(BaseModel):
    email: EmailStr


@router.post("/companies/{tenant_id}/owner")
async def set_owner(tenant_id: UUID, body: OwnerIn, db: TenantDb = Depends(platform_db)):
    """Support action: make an existing active staff user the owner (audited)."""
    await _enter(db, tenant_id)
    m = await db.one("""select m.id from memberships m join profiles p on p.id = m.user_id
                         where p.email = :e and m.status = 'active'""", {"e": body.email})
    if m is None:
        raise bad_request("That person isn't an active user of this company")
    await db.run("update memberships set role = 'tenant_admin' where id = :m", {"m": m["id"]})
    await db.run("update tenants set owner_membership_id = :m where id = :t", {"m": m["id"], "t": tenant_id})
    await _leave(db)
    return {"tenant_id": tenant_id, "owner_membership_id": m["id"]}
```

(An exception rolls back the whole request transaction, so no `_leave` is needed on the error path.)

- [ ] **Step 5:** PASS → commit `feat(P-04): company owner, transfer ownership, platform owner rescue`

### Task C2: Web — owner badge, transfer button

- [ ] session.tsx: `is_owner: boolean` on the session type; `export const isOwner = (ws?: Workspace) => !!ws?.is_owner;`
- [ ] `GET /users` adds `(m.id = (select owner_membership_id from tenants where id = m.tenant_id)) as is_owner`. The users page shows an "Owner" `Chip`. In the drawer, if `isOwner(ws)` and the row is an active staff user other than you, show **Transfer ownership** → confirm `Modal` ("You'll stay an admin. Only the new owner can change roles and permissions.") → `POST /users/{id}/transfer-ownership` → refresh session.
- [ ] Company profile member labels: `super_admin` → "Owner", `owner` → "Co-owner" (`grep -n "super_admin" "apps/web/src/app/(app)/companies/[id]/page.tsx"`).
- [ ] tsc + lint; commit `feat(P-04): web — owner badge and transfer ownership`

---

## Phase D — Roles & permissions (owner-configurable)

### Task D1: Permission core (pure, unit-tested)

**Files:** Create `apps/api/app/permissions.py`, `apps/api/tests/test_permissions_unit.py`

- [ ] **Step 1: Failing test** (first check `ApiError`'s attribute names: `sed -n 1,40p apps/api/app/errors.py`; adapt `.code` / `.message`)

```python
"""pytest tests/test_permissions_unit.py --noconftest"""
import pytest

from app.errors import ApiError
from app.permissions import MODULES, check, effective, required


def test_default_is_full_access_within_the_base_role():
    eff = effective(None, None)
    assert set(eff) == set(MODULES) and set(eff.values()) == {"write"}


def test_override_beats_role_beats_default():
    eff = effective({"invoices": "read", "users": "none"}, {"invoices": "write"})
    assert eff["invoices"] == "write" and eff["users"] == "none" and eff["timesheets"] == "write"


@pytest.mark.parametrize("method,path,want", [
    ("GET", "/v1/invoices", ("invoices", "read")),
    ("POST", "/v1/invoices/abc/payments", ("invoices", "write")),
    ("GET", "/v1/vendor-invoices", ("invoices", "read")),
    ("PATCH", "/v1/sows/1", ("contracts", "write")),
    ("POST", "/v1/insights/ask", ("dashboard", "read")),
    ("GET", "/v1/session", None),
    ("GET", "/v1/notifications", None),
    ("GET", "/v1/invoicesx", None),
])
def test_required(method, path, want):
    assert required(method, path) == want


def test_read_only_blocks_write_but_not_read():
    perms = effective({"invoices": "read"}, None)
    check(perms, "GET", "/v1/invoices", is_owner=False)
    with pytest.raises(ApiError) as e:
        check(perms, "POST", "/v1/invoices", is_owner=False)
    assert e.value.code == "no_permission" and "view-only" in e.value.message


def test_hidden_blocks_reading_and_owner_is_never_blocked():
    perms = effective({"users": "none"}, None)
    with pytest.raises(ApiError):
        check(perms, "GET", "/v1/users", is_owner=False)
    check(perms, "GET", "/v1/users", is_owner=True)
```

- [ ] **Step 2:** `cd apps/api && .venv/Scripts/pytest tests/test_permissions_unit.py --noconftest -v` → FAIL (no module).
- [ ] **Step 3: Implement**

```python
"""Owner-configurable permissions: per module none / read / write, on top of the base role.

Base roles still decide which rows a user sees and which amounts are masked (RLS, RULE-01/02);
a permission can only narrow that. Missing entries mean "write" (= whatever the base role allows).
ponytail: URL-prefix → module map; widening beyond the base role needs the role checks rewritten (P-12).
"""

from __future__ import annotations

from .errors import ApiError

LEVELS = ("none", "read", "write")

# key: (label shown to the owner, URL prefixes after /v1)
MODULES: dict[str, tuple[str, tuple[str, ...]]] = {
    "dashboard": ("Dashboard & insights", ("/dashboard", "/insights")),
    "companies": ("Clients & vendors", ("/companies",)),
    "contracts": ("Contracts, SOWs & e-signatures", ("/agreements", "/contracts", "/sows", "/acceptances", "/envelopes")),
    "projects": ("Projects & placements", ("/projects", "/placements")),
    "consultants": ("Consultants", ("/consultants",)),
    "timesheets": ("Timesheets", ("/timesheets",)),
    "invoices": ("Invoices & payments", ("/invoices", "/vendor-invoices", "/payment-flow", "/payment-runs", "/payments")),
    "pay": ("Payroll, expenses, time off & 1099", ("/expenses", "/form-1099", "/payroll", "/referrals", "/time-off")),
    "compliance": ("Compliance & policies", ("/compliance", "/files", "/policies", "/registrations", "/reminder-rules")),
    "data": ("Import & export", ("/data",)),
    "users": ("Users", ("/users",)),
    "settings": ("Company settings", ("/workspace",)),
    "audit": ("Audit log", ("/audit",)),
}
READ_POSTS = ("/insights/ask",)   # POSTs that only read


def effective(role_perms: dict | None, overrides: dict | None) -> dict[str, str]:
    role_perms, overrides = role_perms or {}, overrides or {}
    return {m: overrides.get(m) or role_perms.get(m) or "write" for m in MODULES}


def required(method: str, path: str) -> tuple[str, str] | None:
    p = path.removeprefix("/v1")
    for key, (_, prefixes) in MODULES.items():
        if any(p == x or p.startswith(x + "/") for x in prefixes):
            return key, "read" if method in ("GET", "HEAD", "OPTIONS") or p in READ_POSTS else "write"
    return None


def check(perms: dict[str, str], method: str, path: str, *, is_owner: bool) -> None:
    need = required(method, path)
    if need is None or is_owner:
        return
    module, action = need
    have = perms.get(module, "write")
    if LEVELS.index(have) < LEVELS.index(action):
        label = MODULES[module][0]
        raise ApiError(403, "no_permission",
                       f"You have view-only access to {label}." if have == "read" else f"You don't have access to {label}.")
```

- [ ] **Step 4:** PASS → commit `feat(P-05): permission core — modules, effective(), check()`

### Task D2: Migration — custom roles + per-user overrides

- [ ] Create `supabase/migrations/20261016000200_roles_permissions.sql`:

```sql
-- =============================================================================
-- myTrakIn · P · 0200 · Owner-configurable roles & permissions
--   custom_roles: a named role built on a base role + a module → none/read/write map
--   memberships.custom_role_id / permission_overrides: per-user assignment and exceptions
--   Only the company owner writes; members of the company can read role names.
-- =============================================================================
set search_path = mytrakin, public, extensions;

create table if not exists custom_roles (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants (id) on delete cascade,
  name        text not null check (length(name) between 2 and 60),
  base_role   text not null check (base_role in ('tenant_admin', 'finance', 'account_manager', 'legal', 'hr',
                                                 'approver', 'viewer', 'vendor_admin', 'client_user', 'consultant')),
  permissions jsonb not null default '{}'::jsonb,
  created_by  uuid,
  created_at  timestamptz not null default now(),
  unique (tenant_id, name)
);

alter table memberships
  add column if not exists custom_role_id       uuid references custom_roles (id) on delete set null,
  add column if not exists permission_overrides jsonb not null default '{}'::jsonb;

alter table custom_roles enable row level security;
drop policy if exists custom_roles_read on custom_roles;
create policy custom_roles_read on custom_roles for select to mytrakin_api using (tenant_id = ctx_tenant());
drop policy if exists custom_roles_write on custom_roles;
create policy custom_roles_write on custom_roles for all to mytrakin_api
  using (tenant_id = ctx_tenant() and (is_account_owner() or ctx_role() = 'system'))
  with check (tenant_id = ctx_tenant() and (is_account_owner() or ctx_role() = 'system'));
grant select, insert, update, delete on custom_roles to mytrakin_api;

drop trigger if exists custom_roles_audit on custom_roles;
create trigger custom_roles_audit after insert or update or delete on custom_roles
  for each row execute function audit_row();
```

(`memberships` is already audited, so role assignments are logged.)
- [ ] `make test` → no migration error. Commit `feat(P-05): custom_roles table + per-user overrides`

### Task D3: Enforce in `tenant_db`; expose in `/session`

- [ ] `_account_state` loads permissions in the same round trip:

```python
async def _account_state(conn, ctx: Ctx) -> dict:
    return (await conn.execute(text(
        """select t.status, t.owner_membership_id = cast(:m as uuid) as is_owner,
                  m.permission_overrides, r.permissions as role_permissions, r.name as custom_role
             from mytrakin.tenants t
             left join mytrakin.memberships m on m.id = :m
             left join mytrakin.custom_roles r on r.id = m.custom_role_id
            where t.id = :t"""), {"t": ctx.tenant_id, "m": ctx.membership_id})).mappings().first()
```

In `tenant_db`, after `_gate(...)`:

```python
        ctx.permissions = permissions.effective(state["role_permissions"], state["permission_overrides"])
        ctx.extra["custom_role"] = state["custom_role"]
        permissions.check(ctx.permissions, request.method, request.url.path, is_owner=ctx.is_owner)
```

Add `permissions: dict = field(default_factory=dict)` to `Ctx`, and `from . import permissions`.
- [ ] `/session`: add `"permissions": ctx.permissions, "custom_role": ctx.extra.get("custom_role")`.
- [ ] Full suite unchanged (everyone defaults to `write`). Commit `feat(P-05): permissions enforced centrally in tenant_db`

### Task D4: Roles API (owner only) + the F1/F2 test

- [ ] **Step 1: Failing test** `apps/api/tests/test_roles.py`

```python
"""Owner builds roles: F1 finance view-only, F2 finance full; per-user override; owner only."""
from sqlalchemy import text

from app.db import get_engine


async def _member(tenant_id, user_id, role="finance"):
    async with get_engine().begin() as conn:
        return (await conn.execute(text(
            """insert into mytrakin.memberships (tenant_id, user_id, role, status) values (:t, :u, :r, 'active')
               on conflict (tenant_id, user_id) where user_id is not null do update set role = excluded.role
               returning id"""), {"t": tenant_id, "u": user_id, "r": role})).scalar()


async def test_f1_read_only_f2_read_write(client, auth, user_ids):
    admin = auth("admin")                                    # demo owner (earliest active tenant_admin)
    s = (await client.get("/session", headers=admin)).json()
    assert s["is_owner"] is True
    await _member(s["tenant"]["id"], user_ids["finance2"])
    role = await client.post("/roles", headers=admin, json={
        "name": "Finance – view only", "base_role": "finance",
        "permissions": {"invoices": "read", "pay": "read", "users": "none"}})
    assert role.status_code == 201, role.text
    f1 = (await client.get("/session", headers=auth("finance"))).json()["membership_id"]
    try:
        assert (await client.patch(f"/users/{f1}/access", headers=admin,
                                   json={"custom_role_id": role.json()["id"]})).status_code == 200
        f1h, f2h = auth("finance"), auth("finance2")
        assert (await client.get("/invoices", headers=f1h)).status_code == 200
        w1 = await client.post("/invoices", headers=f1h, json={})
        assert w1.status_code == 403 and w1.json()["error"]["code"] == "no_permission"
        assert (await client.post("/invoices", headers=f2h, json={})).status_code != 403   # F2 reaches validation
        assert (await client.get("/session", headers=f1h)).json()["permissions"]["invoices"] == "read"
        await client.patch(f"/users/{f1}/access", headers=admin, json={"permission_overrides": {"invoices": "write"}})
        assert (await client.post("/invoices", headers=f1h, json={})).status_code != 403  # override beats role
    finally:
        await client.patch(f"/users/{f1}/access", headers=admin, json={"custom_role_id": None, "permission_overrides": {}})


async def test_only_owner_manages_roles_and_input_is_validated(client, auth):
    assert (await client.get("/roles", headers=auth("finance"))).status_code == 403
    for perms in ({"invoices": "maybe"}, {"invoicez": "read"}):
        r = await client.post("/roles", headers=auth("admin"), json={"name": "Bad", "base_role": "finance", "permissions": perms})
        assert r.status_code == 422
```

If the demo seed has several active `tenant_admin`s, confirm that `admin@example.com` is the earliest (the A1 backfill owner): `select owner_membership_id from mytrakin.tenants` on the test DB. Fix the seed or the test if it isn't.

- [ ] **Step 2: `apps/api/app/routers/roles.py`**

```python
"""Roles & permissions — only the company owner configures them."""

from __future__ import annotations

from uuid import UUID

import orjson
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from ..deps import TenantDb, tenant_db
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
```

- [ ] **Step 3:** main.py: import `roles` and add it to the router tuple (main.py:84).
- [ ] **Step 4:** `pytest tests/test_roles.py -v` → PASS, then the full suite.
- [ ] **Step 5:** Commit `feat(P-06): roles & permissions API — custom roles, per-user access, owner only`

### Task D5: Web — editor, user access, view-only UI

- [ ] session.tsx:

```ts
export type Level = "none" | "read" | "write";
export const perm = (ws: Workspace | undefined, module: string): Level =>
  ws?.is_owner ? "write" : ((ws?.permissions?.[module] as Level) ?? "write");
export const canEdit = (ws: Workspace | undefined, module: string) => perm(ws, module) === "write";
```

(add `permissions: Record<string, Level>` and `custom_role: string | null` to the session type)
- [ ] AppShell nav items get a `module` (`/dashboard` dashboard · `/companies` companies · `/contracts`, `/esign` contracts · `/projects` projects · `/consultants` consultants · `/timesheets` timesheets · `/invoices`, `/payments` invoices · `/pay` pay · `/compliance` compliance · `/data` data · `/users` users · `/settings` settings · `/audit` audit). Add `&& (!item.module || perm(ws, item.module) !== "none")` to the filter. Add a "Roles & permissions" link (`/settings/roles`), shown only when `isOwner(ws)`.
- [ ] `settings/roles/page.tsx` (owner only; others see "Only the company owner can change roles and permissions"): `DataTable id="roles"` (Name, Based on, Members). New/edit opens a `Modal` with Name, Based on (select; locked when editing) and a grid with one row per module from `GET /roles`, using radios **Hidden / View / Edit** (default Edit). Helper line: "A role can only narrow what its base role allows." Delete with confirm.
- [ ] Users drawer (owner only): "Access" section with Role ("Default for {base role}" + custom roles) and "Exceptions for this person" (per module: **Inherit / Hidden / View / Edit**; Inherit = key omitted) → `PATCH /users/{id}/access`.
- [ ] Hide create/edit actions when view-only, with `canEdit(ws, module)`:

| Page(s) | module |
|---|---|
| `invoices/**`, `payments/**` | `invoices` |
| `timesheets/**` | `timesheets` |
| `contracts/**`, `esign/**` | `contracts` |
| `projects/**` | `projects` |
| `consultants/**` | `consultants` |
| `companies/**` | `companies` |
| `compliance/page.tsx` | `compliance` |
| `pay/page.tsx` | `pay` |
| `data/page.tsx` | `data` |
| `users/page.tsx` | `users` |
| `settings/page.tsx` | `settings` |

Pattern: `<PageHead title="Invoices" actions={canEdit(ws, "invoices") && <button className="btn pri" …>New invoice</button>} />`. The API is the real guard: a missed button just gets the 403 "You have view-only access to Invoices & payments."
- [ ] tsc + lint + manual check (owner makes "Finance – view only" for test.finance; no "New invoice" button; a direct call returns 403). Commit `feat(P-06): web — roles & permissions editor, per-user access, view-only UI`

---

## Phase E — MFA: the user's choice (nobody forced)

### Task E1: Migration + test stub

- [ ] Create `supabase/migrations/20261016000300_user_mfa.sql`:

```sql
-- =============================================================================
-- myTrakIn · P · 0300 · Two-step verification is the user's choice (owner decision 2026-10-15)
--   memberships.mfa_allowed   the owner offers (true) or withholds (false) the option per user
--   user_has_mfa(uid)         did this person turn MFA on? (verified factor in Supabase Auth)
--   mfa_allowed_for(uid)      may they turn it on? (any active membership allows, or none yet)
-- =============================================================================
set search_path = mytrakin, public, extensions;

alter table memberships add column if not exists mfa_allowed boolean not null default true;

create or replace function user_has_mfa(p_user uuid) returns boolean
language plpgsql stable security definer set search_path = mytrakin, public, extensions as $$
declare found boolean := false;
begin
  if to_regclass('auth.mfa_factors') is not null then   -- absent in bare local test databases
    execute 'select exists (select 1 from auth.mfa_factors where user_id = $1 and status = ''verified'')'
       into found using p_user;
  end if;
  return found;
end $$;

create or replace function mfa_allowed_for(p_user uuid) returns boolean
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select coalesce(bool_or(mfa_allowed), true) from memberships where user_id = p_user and status = 'active'
$$;

revoke all on function user_has_mfa(uuid), mfa_allowed_for(uuid) from public;
grant execute on function user_has_mfa(uuid), mfa_allowed_for(uuid) to mytrakin_api;
```

- [ ] conftest (after conftest.py:65): first check `grep -n "auth" scripts/db-local-reset.sh` to see whether the real auth schema is loaded; `if not exists` makes it safe either way.

```python
        await conn.execute(text("""create table if not exists auth.mfa_factors (
                                     id uuid primary key default gen_random_uuid(), user_id uuid not null,
                                     status text not null default 'verified')"""))
```

### Task E2: Replace the money-role gate

- [ ] **Step 1: Failing test** `apps/api/tests/test_mfa_choice.py`

```python
"""MFA is the user's choice: nobody forced; once on, an aal1 token is refused."""
from sqlalchemy import text

from app.db import get_engine


async def test_finance_not_forced_into_mfa(client, auth):
    assert (await client.get("/dashboard", headers=auth("finance", aal="aal1"))).status_code == 200


async def test_mfa_on_requires_second_step(client, auth, user_ids):
    async with get_engine().begin() as conn:
        await conn.execute(text("insert into auth.mfa_factors (user_id, status) values (:u, 'verified')"),
                           {"u": user_ids["consultant"]})
    try:
        r = await client.get("/session", headers=auth("consultant", aal="aal1"))
        assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_required"
        assert (await client.get("/session", headers=auth("consultant", aal="aal2"))).status_code == 200
    finally:
        async with get_engine().begin() as conn:
            await conn.execute(text("delete from auth.mfa_factors where user_id = :u"), {"u": user_ids["consultant"]})


async def test_owner_allocates_mfa_option(client, auth):
    admin = auth("admin")
    fid = (await client.get("/session", headers=auth("finance"))).json()["membership_id"]
    try:
        assert (await client.patch(f"/users/{fid}", headers=admin, json={"mfa_allowed": False})).status_code == 200
        assert (await client.get("/me", headers=auth("finance"))).json()["mfa_allowed"] is False
    finally:
        await client.patch(f"/users/{fid}", headers=admin, json={"mfa_allowed": True})
```

Delete `test_money_roles_need_mfa` (test_access.py:34-39).
- [ ] **Step 2:** Run → FAIL (finance aal1 gets 403 today).
- [ ] **Step 3: Implement**
  - Add `, mytrakin.user_has_mfa(:uid) as has_mfa` to the select lists of `_START_SQL` and `_COMPANY_TENANT_SQL`.
  - Replace both `require_mfa_for_money_roles` blocks with `_mfa_gate(row, claims)` in `tenant_db`, `member_db` (membership branch), and `onboarding_db`:

```python
def _mfa_gate(row, claims: Claims) -> None:
    """Two-step is the user's choice; once they turn it on, every session must finish it."""
    if row["has_mfa"] and claims.aal != "aal2":
        raise ApiError(403, "mfa_required", "Finish two-step verification to continue.")
```

  - `member_db` no-membership branch, `user_db` and `platform_db`: `if claims.aal != "aal2" and (await conn.execute(text("select mytrakin.user_has_mfa(:u)"), {"u": claims.user_id})).scalar(): raise ApiError(403, "mfa_required", …)`.
  - Delete `MONEY_ROLES` (deps.py), `require_mfa_for_money_roles` (config.py:53), and every `REQUIRE_MFA_FOR_MONEY_ROLES` mention (`grep -rn "REQUIRE_MFA\|require_mfa" .` → `.env.example`, `docs/deployment.md`, `supabase/config.toml` …). Also update the memory note "Local test setup" afterwards.
  - admin.py `MembershipPatch`: `mfa_allowed: bool | None = None`. `list_users` select: `m.mfa_allowed, mytrakin.user_has_mfa(m.user_id) as mfa_on`.
  - me.py `/me`: `"mfa_allowed": bool(await db.val("select mytrakin.mfa_allowed_for(:u)", {"u": uid}))`.
- [ ] **Step 4:** Full suite → PASS. Commit `feat(P-07): MFA is the user's choice — owner allocates, no role forcing; MFA-on requires aal2`

### Task E3: Web — Account toggle, users column

- [ ] Account → "Two-step verification" card: factors exist → **On** + **Turn off** (existing unenroll, account/page.tsx:56; always shown, so someone whose option was withdrawn can still switch it off). No factors and `me.mfa_allowed` → **Off** + **Turn on** (`/login?step=mfa&next=/account`). No factors and not allowed → "Your company owner hasn't enabled two-step verification for your account."
- [ ] login `MfaStep`: if there are no factors and `me.mfa_allowed === false`, show that sentence instead of the QR code.
- [ ] AppShell `mfa_required` copy → "You turned on two-step verification. Enter your code to continue." (the link verifies; it doesn't set up).
- [ ] Users page: column "2-step" = On / Off / Not offered. The drawer (owner/admin) has a switch "Allow two-step verification" → `PATCH /users/{id}` `{mfa_allowed}`.
- [ ] tsc + lint; manual check with test.finance (on → sign in asks for code → off). Commit `feat(P-07): web — MFA on/off in Account, option per user`

---

## Phase F — Platform analytics dashboard

### Task F1: SQL aggregates (append to migration 0400)

- [ ] First check that `profiles.created_at` exists (`grep -n "create table mytrakin.profiles" -A12 supabase/migrations/20261011000100_foundation.sql`). If it doesn't, use `auth.users.created_at` (the function is security definer).

```sql
-- Money moving through each company: totals only, never rows.
create or replace function platform_money_stats()
returns table (tenant_id uuid, ar_invoiced numeric, ar_collected numeric, ap_billed numeric, ap_paid numeric,
               invoiced_30d numeric, collected_30d numeric)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  with inv as (
    select i.tenant_id, i.direction, sum(i.amount) as total,
           sum(i.amount) filter (where i.issued_on > current_date - 30) as last30
      from invoices i where i.status not in ('draft', 'void') group by 1, 2),
  pay as (
    select p.tenant_id, i.direction, sum(p.amount) as total,
           sum(p.amount) filter (where p.paid_on > current_date - 30) as last30
      from payments p join invoices i on i.id = p.invoice_id
     where p.status in ('completed', 'confirmed') group by 1, 2)
  select t.id,
         coalesce((select total  from inv where inv.tenant_id = t.id and direction = 'ar'), 0),
         coalesce((select total  from pay where pay.tenant_id = t.id and direction = 'ar'), 0),
         coalesce((select total  from inv where inv.tenant_id = t.id and direction = 'ap'), 0),
         coalesce((select total  from pay where pay.tenant_id = t.id and direction = 'ap'), 0),
         coalesce((select last30 from inv where inv.tenant_id = t.id and direction = 'ar'), 0),
         coalesce((select last30 from pay where pay.tenant_id = t.id and direction = 'ar'), 0)
    from tenants t
   where is_platform_admin()
$$;

create or replace function platform_money_trend()
returns table (month text, invoiced numeric, collected numeric)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  with months as (select to_char(d, 'YYYY-MM') as month
                    from generate_series(date_trunc('month', now()) - interval '11 months',
                                         date_trunc('month', now()), interval '1 month') d)
  select m.month,
         coalesce((select sum(i.amount) from invoices i where i.direction = 'ar' and i.status not in ('draft', 'void')
                    and to_char(i.issued_on, 'YYYY-MM') = m.month), 0),
         coalesce((select sum(p.amount) from payments p join invoices i on i.id = p.invoice_id
                    where i.direction = 'ar' and p.status in ('completed', 'confirmed')
                      and to_char(p.paid_on, 'YYYY-MM') = m.month), 0)
    from months m
   where is_platform_admin()
   order by m.month
$$;

create or replace function platform_overview()
returns table (total_users bigint, new_users_30d bigint, active_users_30d bigint,
               wizards_in_progress bigint, wizards_completed_30d bigint)
language sql stable security definer set search_path = mytrakin, public, extensions as $$
  select (select count(*) from profiles),
         (select count(*) from profiles where created_at > now() - interval '30 days'),
         (select count(distinct user_id) from memberships where last_active_at > now() - interval '30 days'),
         (select count(*) from onboarding_sessions s join tenants t on t.id = s.tenant_id
           where t.status = 'onboarding' and s.status in ('draft', 'email_verified') and s.expires_at > now()),
         (select count(*) from onboarding_sessions s join tenants t on t.id = s.tenant_id
           where t.company_id = s.company_id and s.status = 'complete' and s.created_at > now() - interval '30 days')
   where is_platform_admin()
$$;

revoke all on function platform_money_stats(), platform_money_trend(), platform_overview() from public;
grant execute on function platform_money_stats(), platform_money_trend(), platform_overview() to mytrakin_api;
```

### Task F2: `/platform/metrics` v2 + per-company money

- [ ] **Step 1: Failing test** `apps/api/tests/test_platform_analytics.py`

```python
async def test_platform_metrics_cover_the_platform(client, auth):
    assert (await client.get("/platform/metrics", headers=auth("finance"))).status_code == 403
    m = (await client.get("/platform/metrics", headers=auth("platform"))).json()
    assert {"users", "companies", "pipeline", "revenue", "money", "activity"} <= set(m)
    assert m["users"]["total"] >= 6 and m["companies"]["active"] >= 1
    assert [s["stage"] for s in m["pipeline"]] == ["Wizard in progress", "Waiting for activation", "Active", "Suspended / closed"]
    assert len(m["money"]["trend"]) == 12
    assert float(m["money"]["ar_outstanding"]) == float(m["money"]["ar_invoiced"]) - float(m["money"]["ar_collected"])


async def test_platform_company_rows_hold_only_totals(client, auth):
    rows = (await client.get("/platform/tenants", headers=auth("platform"))).json()
    assert rows and {"ar_invoiced", "ar_collected", "ap_paid"} <= set(rows[0])
    assert not {"number", "invoice_id", "rate"} & set(rows[0])      # no invoice-level data
```

- [ ] **Step 2: Implement** (platform.py)

```python
async def _tenants(db: TenantDb) -> list[dict]:
    rows = await db.all(
        """select t.id, t.name, t.legal_name, t.state, t.plan, t.status, t.onboarding_step, t.trial_ends_on, t.live_on,
                  t.created_at, t.activated_at, s.active_users, s.invited_users, s.consultants, s.active_placements,
                  s.last_user_activity, ms.ar_invoiced, ms.ar_collected, ms.ap_billed, ms.ap_paid,
                  ms.invoiced_30d, ms.collected_30d
             from tenants t join mytrakin.platform_tenant_stats() s on s.tenant_id = t.id
             join mytrakin.platform_money_stats() ms on ms.tenant_id = t.id
            order by t.created_at desc""")
    for r in rows:
        billable = r["status"] == "active" and not (r["trial_ends_on"] and r["trial_ends_on"] >= date.today())
        r["mrr"] = PRICE_PER_USER[r["plan"]] * r["active_users"] if billable else Decimal(0)
        r["price_per_user"] = PRICE_PER_USER[r["plan"]]
    return rows


@router.get("/metrics")
async def metrics(db: TenantDb = Depends(platform_db)):
    tenants = await _tenants(db)
    o = await db.one("select * from mytrakin.platform_overview()")
    trend = await db.all("select * from mytrakin.platform_money_trend()")
    pending = await db.val(
        "select count(*) from mytrakin.platform_companies() where status = 'onboarding' and company_id is not null")
    by = {s: sum(1 for t in tenants if t["status"] == s) for s in ("onboarding", "active", "suspended", "closed")}
    paying = [t for t in tenants if t["mrr"] > 0]
    mrr = sum((t["mrr"] for t in tenants), Decimal(0))

    def tot(k: str) -> Decimal:
        return sum((t[k] for t in tenants), Decimal(0))

    month_ago, two_weeks_ago = date.today() - timedelta(days=30), date.today() - timedelta(days=14)
    return {
        "users": {"total": o["total_users"], "new_30d": o["new_users_30d"], "active_30d": o["active_users_30d"],
                  "active_in_companies": sum(t["active_users"] for t in tenants)},
        "companies": {"total": len(tenants), "active": by["active"], "pending_activation": pending or 0,
                      "suspended": by["suspended"], "closed": by["closed"],
                      "new_30d": sum(1 for t in tenants if t["created_at"].date() >= month_ago),
                      "inactive_14_days": [t["name"] for t in tenants if t["status"] == "active" and
                                           (t["last_user_activity"] is None or t["last_user_activity"].date() < two_weeks_ago)]},
        "pipeline": [{"stage": "Wizard in progress", "count": o["wizards_in_progress"]},
                     {"stage": "Waiting for activation", "count": pending or 0},
                     {"stage": "Active", "count": by["active"]},
                     {"stage": "Suspended / closed", "count": by["suspended"] + by["closed"]}],
        "revenue": {"mrr": mrr, "arr": mrr * 12, "paying_companies": len(paying),
                    "arpu": (mrr / sum(t["active_users"] for t in paying)).quantize(Decimal("0.01")) if paying else Decimal(0),
                    "by_plan": {p: sum((t["mrr"] for t in tenants if t["plan"] == p), Decimal(0)) for p in PRICE_PER_USER}},
        "money": {"ar_invoiced": tot("ar_invoiced"), "ar_collected": tot("ar_collected"),
                  "ar_outstanding": tot("ar_invoiced") - tot("ar_collected"),
                  "ap_billed": tot("ap_billed"), "ap_paid": tot("ap_paid"),
                  "invoiced_30d": tot("invoiced_30d"), "collected_30d": tot("collected_30d"), "trend": trend},
        "activity": {"consultants": sum(t["consultants"] for t in tenants),
                     "active_placements": sum(t["active_placements"] for t in tenants)},
        "growth": await db.all(
            """select to_char(date_trunc('month', created_at), 'YYYY-MM') as month, count(*) as new_companies
                 from tenants where created_at > now() - interval '12 months' group by 1 order by 1"""),
    }
```

- [ ] Update `test_platform_console_is_owner_only` (test_access.py:97): `metrics["companies"]["total"] >= 1 and metrics["users"]["active_in_companies"] >= 1`.
- [ ] PASS → commit `feat(P-08): platform analytics — users, companies, pipeline, SaaS revenue, money moving`

### Task F3: Web — Overview dashboard

Load the `dataviz` skill before writing the chart code. No chart library: CSS bars plus inline SVG, matching the existing `Kpi` component.

- [ ] `overview` tab (default):
  - KPI row 1: Total users (detail "new 30 d · active 30 d"), Companies ("{active} active · {pending} waiting"), MRR (ARR), Revenue per user.
  - KPI row 2, "Money moving through myTrakIn": Invoiced to clients (last 30 d), Collected (last 30 d), Outstanding AR, Paid to vendors.
  - **Onboarding pipeline**: 4 horizontal bars (width = count / max). "Waiting for activation" opens the queue tab.
  - **Money trend**: 12 months, grouped invoiced vs collected (`money(v, true)`).
  - **Companies needing attention**: `inactive_14_days`.
- [ ] `companies` tab = the old tenants table, with header "Company" and new money columns Invoiced / Collected / AP paid (`type: "money"`). The drawer keeps plan/status/trial and adds "Make owner" (e-mail → `POST /platform/companies/{id}/owner`).
- [ ] Title "Platform admin", sub "Every company on myTrakIn, how it's growing, and the money moving through it." AppShell nav "Owner console" → "Platform admin".
- [ ] Phone width + dark mode (DoD). tsc + lint. Commit `feat(P-08): web — platform analytics dashboard`

---

## Phase G — Cron, wording, docs, verification

### Task G1: Purge abandoned drafts

- [ ] Read `cron.daily()` (cron.py:44) and follow its connection pattern: call `select mytrakin.purge_abandoned_accounts()` once (not per tenant) and add `"purged_accounts": n` to its response. Test: insert a tenant `status='onboarding', company_id null, created_at = now() - interval '8 days'`, call `/cron/daily` with the cron secret, and assert it is gone. Commit `feat(P-01): purge company drafts abandoned for 7 days`

### Task G2: "Workspace" → "company" in the product

- [ ] `grep -rn -i "workspace" apps/web/src apps/api/app --include=*.tsx --include=*.ts --include=*.py`. Change **user-visible text only**: pages, error messages (deps.py "You don't have access to this workspace yet…" → "You don't have access to this company yet. Ask its owner for an invite."), and e-mails. Keep identifiers, API paths (`/workspace`, `/public/workspaces/…`), `X-Tenant-Id` and type names; renaming them is churn with no user value. The switcher becomes the "company switcher" (label only).
- [ ] Commit `chore(P-09): say company, not workspace, everywhere users can see`

### Task G3: Docs

- [ ] `docs/PLAN.md`: new **§5.31 Platform admin, ownership, permissions, MFA (Phase P)**: P-01 company accounts · P-02 platform activation · P-03 platform admins · P-04 owner + transfer · P-05 permission core · P-06 roles UI/API · P-07 MFA choice · P-08 analytics · P-09 wording · P-10 RULE-05 amendment · P-11 sign-up requests removed · **P-12 ❌ follow-up: permissions that widen beyond the base role**. Amend RULE-05 per D-P6. Phase P in §7; a line in §9.
- [ ] `docs/security.md`: MFA = user's choice, owner allocates, enforced on every API call once on; record the owner decision (2026-10-15) that drops forced MFA for money roles. SEC-08 → `roles.py` validation.
- [ ] `docs/functional.md`, `docs/technical.md` (company = tenant; permission gate in `tenant_db`), `CHANGELOG.md`, `docs/api-reference.md` (regenerate: `scripts/gen-api-reference.py`).
- [ ] Commit `docs(P): Phase P — plan, security, functional, technical, changelog`

### Task G4: Verification (PLAN §0 Definition of Done)

- [ ] `make check` → green.
- [ ] `cd apps/api && .venv/Scripts/pytest -q` on a fresh local DB → every new test passes. The only failures allowed are the 2 known team W-9 tests; name them in the report.
- [ ] Browser QA (chrome-devtools, isolated page per role; the owner types the passwords):
  1. New user → create company → waiting screen.
  2. Platform admin → queue → review W-9 → Activate → owner gets the e-mail.
  3. Owner invites F1 + F2 (finance) → "Finance – view only" on F1 → F1 sees invoices but no buttons, a direct POST → 403; F2 creates an invoice.
  4. Owner transfers ownership → new owner sees "Roles & permissions", old owner doesn't.
  5. F2 turns MFA on → next sign-in asks for a code → turns it off. Owner withdraws F1's option → F1 sees the "not enabled" sentence.
  6. Platform dashboard totals = a manual SQL sum for one company.
  7. Phone width + dark mode on the dashboard and the roles editor.
- [ ] Hostile self-review: RLS on `custom_roles`; can a non-owner reach `/roles`; does any platform endpoint return invoice rows; do counterparty activations still work inside active companies; does a pending company reach anything outside `PENDING_OK`.
- [ ] Production: hand the owner the 4 migrations (0100 → 0400, one transaction). **Existing companies are already `active`, so nothing gets blocked; only new registrations wait for activation.** Push only on the owner's go-ahead (`! git push origin main`).

---

## Self-review

- **Coverage:** platform admin role + management (B2) ✔ · analytics: total users, companies onboarded/active, onboarding pipeline, SaaS revenue, money moving (F1–F3) ✔ · req 1: any user creates, platform activates, activation is platform-only for the company itself (A3, B1) ✔ · req 2: owner + transfer (A1, C1, C2) ✔ · req 3: custom roles + per-user (F1/F2) + defaults (D1–D5) ✔, with the narrowing-only limit stated (A5 / P-12) · req 4: MFA user's choice, owner allocates, nobody forced (E1–E3) ✔ · "no workspace" (A4, G2) ✔.
- **Names consistent across tasks:** `start_company_account(uuid)`, `is_account_owner()`, `_account_state`, `_gate`, `ctx.is_owner`, `ctx.permissions`, `permissions.effective/required/check`, `custom_roles`, `permission_overrides`, `mfa_allowed`, `user_has_mfa`, `mfa_allowed_for`, `_mfa_gate`, `platform_companies/money_stats/money_trend/overview`, `_enter/_leave`.
- **Facts the implementer must check first** (each named in its task): `ApiError` attribute names; the `platform_admins` write policy; `profiles.created_at`; `companies.onboarding_stage` type; the auth schema in `db-local-reset.sh`; the seed's owner backfill; the `cron.daily` connection pattern.
