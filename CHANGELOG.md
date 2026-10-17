# Changelog

## Unreleased

- **Agreements are visible to the company they are with (2026-10-16, PLAN AGR-07):** an MSA recorded in one workspace
  now appears, read-only, in the counterparty company's workspace — terms from its own side ("Received from …"),
  plus the files attached to it. The counterparty can download but can't edit, add files, sign for the sender, or see
  the sender's SOWs and signatures. Migration `20261016001200`.
- **Company IDs are unique platform-wide; no agreement with the company itself (2026-10-16, PLAN CO-03, AGR-07):**
  - Business IDs (`C-0001` …) come from one platform sequence and are unique across all companies. Previously each
    workspace numbered its own, so several companies shared `C-0001`; the earliest keeps its ID and the others were
    renumbered (migration `20261016001100`).
  - An agreement can't be between a company and itself: the API refuses it, and the counterparty picker never offers
    the workspace's own company (or the company the MSA is opened from).
- **Cross-tenant company directory (2026-10-16, PLAN CO-03, AGR-07):** the company picker lists every active
  company in the database, not just the current tenant's — an MSA counterparty can be any registered business.
  Only directory columns (ID, name, roles) are shared; profiles, money and contacts stay behind tenant RLS, and
  agreements still book to the requester's tenant (RULE-01). Migration `20261016001000`.
- **Agreement entry UX (2026-10-16, PLAN CO-03, AGR-07):** the agreement number is always auto-assigned (the
  Agreement ID box is gone from the Add-agreement form); the company picker is now a type-ahead with suggestions
  (plus honest loading/error states instead of a blanket "no match"); the consultant picker shows name + U-ID.
- **Several roles per company (2026-10-16, PLAN CO-01, CO-02):** "What does your company do?" is multi-select —
  a business can be a vendor on one engagement and a client on another. `companies.kinds` holds every role;
  `kind` stays the primary (first ticked) so filters, labels, imports and exports keep working. Creation doesn't
  ask at all — a new business starts with all four roles (narrow them on the company profile if ever needed).
  Migration `20261016000900` (backfills `kinds` from `kind`).
- **Discardable company drafts (2026-10-16, PLAN P-01):** closing the create-company wizard early left an invisible
  draft that still counted toward the 3-pending cap. Unfinished setups now show on My companies with Resume
  (continues inside the same draft account) and Discard (`DELETE /onboarding/accounts/{id}`, owner only, drafts
  only — submitted companies still wait for the platform decision). Migration `20261016000800`.
- **W-9 extraction fix (2026-10-16):** a March-2024 W-9 whose section-1 label wraps mid-sentence across two lines
  no longer bleeds the wrap ("entity's name on line 2.)") into `legal_name` — e.g. DREP Software solution parses
  exactly. The line-1 label's own mention of "disregarded" also no longer misfiles filled-PDF line-1 values as the
  DBA (which left `legal_name` empty with "couldn't find the legal name"). Regression tests in `tests/test_w9_parse.py`.
- **Fixes from a live click-through of the money flow (2026-10-16):**
  - A consultant can fix and resubmit a week their approver returned (saving a returned week failed with
    "You don't have permission to do that" — the RLS update policy didn't allow the row to stay `rejected`).
  - The daily job no longer sends customer reminders for **draft** AR invoices that were never sent.
  - Vendors and 1099 payees see pay-when-paid invoices as **held** (they saw "ready to pay": the held check couldn't
    read the client invoice under the payee's row-level security). AR amounts stay hidden.
  - A consultant's U-ID now shows after they sign up from an invite (`consultants.user_id` was never linked).
  - Dates in the browser use the local day, not UTC: "Create invoices from timesheets" defaulted to Aug 31 – Sep 29
    instead of Sep 1 – 30 east of UTC (India); payment dates and export file names had the same off-by-one.
  - E-signature completion e-mail: one copy per address when the sender also signed.

- **Company-initiated MSAs** (PLAN CO-03, AGR-07): searchable company directory (`GET /companies/directory`) and
  `POST /companies/{id}/msas` so a company's owner/admin — or its membership-linked vendor/client admin — records an
  already-signed MSA or requests a new one from the company profile (NDA gate and numbering apply; counterparty gets
  an e-mail). Migration `0800` lets those membership-linked admins pass the agreements INSERT policy (was 403).
- **Companies, platform admin, ownership, roles & permissions, MFA** (PLAN §5.31):
  - No workspaces: anyone creates a company (My companies → Create your company); it waits for the platform admin.
  - Platform admin: dashboard (users, companies, onboarding pipeline, MRR/ARR, money moving, 12-month trend),
    activation queue with W-9 review (activate / ask for more / reject), platform admin management, owner rescue.
  - One owner per company; **Transfer ownership**; the owner can't be demoted.
  - Owner-only **Roles & permissions**: custom roles (per module hidden / view / edit) and per-person exceptions.
  - Two-step verification is each user's choice; the owner can withhold the option per user. Forced MFA for admin
    and finance is removed (`REQUIRE_MFA_FOR_MONEY_ROLES` no longer exists).
  - The public "request a workspace" form and "Create workspace" are gone.
- **Approved workflow** (owner e-mail 2026-10-15, PLAN §5.30): Register → Verify → NDA → MSA → Project → SOW →
  Acceptance → Resource contract → Acceptance → Timesheet → Invoice → Payment → Payment confirmation.
  - Settings → Workflow: switches `requireNDA`, `requireMSA`, `requireContract`, `requireAcceptance` (default on).
  - NDA needed before a company's MSA and before a project with it is activated; MSA needed for project activation,
    client invoices and vendor payments; no new SOWs under an expired agreement.
  - SOWs and work orders belong to a project (`POST /projects/{id}/sows`); one SOW carries one or many resources
    (`GET/POST /sows/{id}/resources`), each with its own contract, timesheets, invoices and payments.
  - Timesheets need the resource's contract (vendor / 1099 work order or W-2 offer letter) and its acceptance.
  - Acceptance records: e-signature completion records one; staff can record paper / e-mail acceptance; history shown
    on agreement and SOW pages.
  - Engagement types are a table (W-2 full-time, W-2 contract, C2C, **E2E (employer-to-employer)**, 1099).
  - Numbering templates per document type in Settings → Numbering (`PROJ-{YEAR}-{SEQ:3}`, `INV-{YYYYMM}-{SEQ}` …).
  - Payments move pending → processing → completed → **confirmed**; finance or the payee confirms.
- Fixes: a Super Admin counts as company owner for activation; an approved timesheet can no longer be reopened after
  its hours are invoiced (the change was silently never billed); timesheet reminder e-mails link to `/my/timesheet`.

- A new person who signs in (Google, Microsoft or e-mail) without a workspace now lands on the Network feed with a
  limited menu (Network, My businesses, My profile, Account & security) instead of a "request a workspace" screen.
  The network API works without a workspace; posts default to "Everyone in my network".
- Sign-in: forgot-password flow (`/reset-password`); Google and Microsoft buttons on sign-in and create-account
  (hidden while a provider is switched off in Supabase); clearer sign-in error messages; "cancel and sign out" on the
  two-step verification screen. Setup steps: `docs/auth-setup.md`.

## 1.0.0 — 2026-10-12

First production release of **myTrakIn** (renamed from the VendorChain prototype).

- Multi-tenant SaaS with owner console, sign-up approval, plans and revenue per user
- Payment flow across the vendor chain with the AR/AP-only rule
- AR invoices from approved timesheets, collections, reminders; AP with three-way match, pay-when-paid, payment runs
- Weekly multi-project timesheets with automatic checks and bulk approval
- Onboarding for W-2 full-time, W-2 contract, C2C and 1099; offboarding, former staff, rehire
- MSAs, subcontracts, NDAs, offers, contractor agreements, SOWs and amendments; record existing contracts
- E-signatures with e-mail code, ESIGN/UETA consent, IP/device/location evidence and sealed PDF certificate
- Compliance: I-9 / work authorization, expiring documents with automatic e-mails, policies, public registration
- W-2 payroll records, referral fees, 1099 year-end summary, expenses and time off
- CSV templates, dry-run import, export for every data set
- LinkedIn-style profiles, connections, posts and messages
- Smart suggestions with optional AI answers
- Audit log of every change with IP address and before/after values
- Next.js 16 web app and FastAPI API on Vercel; Supabase Postgres (RLS), Auth (codes, SSO, OAuth, MFA) and Storage
