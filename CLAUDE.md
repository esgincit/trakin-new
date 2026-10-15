# myTrakIn — start here (every session)

Multi-tenant SaaS for US IT staffing companies: payments (AR/AP), timesheets, contracts, e-signatures and compliance
across the vendor chain. Built to match the customer's clickable prototype.

## Read first, in this order
1. `docs/PLAN.md` — requirement IDs with status (✅ / 🟡 / ❌), the work order (§7) and the progress log (§9, newest
   first — tells you where the last session stopped).
2. `docs/prototype-spec.md` — complete written spec of every prototype screen, field, button, message, formula and
   constant. Read the section for the item you are building (tags like `[AR]` match PLAN ID prefixes).
3. `docs/prototype/mytrakin-prototype.html` — the original prototype (single HTML file, demo data, role switcher).
   Final word when the spec is unclear. It is large (440 KB); grep it (`VIEWS.<id>=` defines each screen) rather than
   reading it whole.
4. `README.md`, `docs/technical.md`, `docs/functional.md` — how the product is built and run.
5. `docs/legacy-contrack.md` — what is (and is not) taken from the old Contrack project: Zoho SMTP settings and a
   security/billing-test checklist only. **Never copy or implement functionality from the old project** (owner's rule,
   PLAN RULE-07); the prototype is the requirement, **except where the owner's e-mail spec
   `docs/requirements/2026-10-15-mail-master-spec.md` differs — the e-mail wins** (PLAN §5.30, Phase W).
Then run `git status` — uncommitted work from a previous session is the thing most likely to be missed.

## How to work an item
- Take the top open item in PLAN.md §7 unless the user names one. Use its ID in branch/commit/PR names.
- Follow the Definition of Done in PLAN.md §0 (role checks, API test, RLS for new tables, audit, DataTable lists,
  phone + dark mode, `make check`, docs, CHANGELOG).
- In the same change: update the item's status in PLAN.md and add a line to PLAN.md §9.
- Never break the rules in PLAN.md §1 (RULE-01…06), above all **AR/AP only** (never store rates of links the tenant
  is not party to) and role-based amount masking.

## Layout
`apps/api` FastAPI (routers in `app/routers`, services in `app/services`, tests in `tests`) · `apps/web` Next.js 16
App Router (`src/app`, `src/components`, `src/lib`; see `apps/web/AGENTS.md`) · `supabase/migrations` (new migration
per change, never edit an applied one) · `docs/`.

Commands: `make setup`, `make api`, `make web`, `make test`, `make check`.
