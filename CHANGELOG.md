# Changelog

## Unreleased



- **Weekend hours need the consultant's confirmation (2026-10-21):** approving a week with weekend hours is
  blocked until the consultant confirms them. The approver clicks "Ask consultant to confirm weekend hours"
  (optional note), the consultant gets an e-mail and a banner in My timesheet with a "Confirm weekend hours"
  button; confirming e-mails the approver and lifts the gate. Returning a week for changes also e-mails the
  consultant the reason, and rejecting / resubmitting clears the weekend confirmation so every round starts
  fresh. Migration 20261021000100_timesheet_weekend_confirmation.sql - apply to production before deploying.
- **Two-level timesheet approval fixed (2026-10-21):** "Placed By" approval is the placing workspace's own
  approval (it was wrongly matched against the vendor we pay); the end client approves when the placement has
  one, and weeks without an external end client finalise on the placing company's approval alone. Migration
  20261020000100_timesheet_two_level_approval.sql **must be applied to production** (it was committed on
  2026-10-20 but never applied - every timesheet save / submit / approve returned 500 on the live DB until now).
- **QA tickets T011303-1037, 1045–1049 (2026-10-19):**
  - **Project with an MSA counterparty (1049):** the client / prime lists on New project only showed companies in
    your own workspace, so the company you have an MSA with could not be chosen and the project failed with "no
    active MSA". Both lists now include every company you have an MSA in force with, whichever side sent it, and
    the MSA check also counts an MSA the other company sent you. Project and placement pages show that company's
    name (it was blank / "Internal").
  - **Projects assigned to you (1047):** New placement lists your active projects plus projects another company
    assigned to you by sending a SOW / work order ("from …"). Placing someone on one creates your own copy of the
    project (prime = that company, bill-to defaults to it); timesheets, invoices and rates stay in your workspace.
  - **MSA terms are dropdowns (1048):** payment terms (Net 15–90), renewal, notice period and insurance required.
  - **No admin access before your company exists (1037):** a company still being set up or waiting for activation
    shows only the network / My companies menu and no "tenant admin" role; admin pages explain how to finish setup.
  - **E-mail delivery (1045, 1046):** our log shows the consultant and offer-letter mails were handed to the mail
    server immediately; delays happen after that. Mails now carry Date and Message-ID headers and a real plain-text
    part (fewer spam / deferral flags); the consultant mail's subject says "… added you as a consultant".
    The sending domain has no DMARC record — add one in DNS.
  - Migration `20261019000100_shared_projects.sql` — apply to production **before** deploying.

- **Credit notes, adjustment after invoicing, time off on the timesheet (2026-10-18, PLAN AR-06, TS-07, TS-10):**
  - Finance can issue a **credit note** against a sent client invoice — up to its open balance (payments still in
    flight count against it), with a reason, numbered `CN-2026-0001` (editable in Settings → Numbering). The
    invoice balance, aging and dashboards drop at once; a client invoice fully settled by payments plus credits is
    paid and releases its pay-when-paid vendor invoices. Invoices with credit notes can't be voided.
    New **Credit notes** tab on Invoices (open → applied once the invoice is settled); credits listed on the invoice.
  - Re-opening an approved week that is already invoiced now names the invoice and says what to do: void it if
    nothing is paid, otherwise a credit note (fewer hours) or an extra invoice (more hours). Approved weeks show
    **Request adjustment**.
  - Approved time off appears as a read-only row on **My timesheet** (not saved as hours, never billed).
  - Migration `20261018000100` (table `credit_notes`, `invoice_balances.credited`) — apply to production **before**
    deploying this code: `/invoices` reads the new column.

- **"E-mail codes aren't going out" was really a one-minute cooldown (2026-10-17):** Supabase allows only one
  sign-in code per address per minute, and a second request returns `over_email_send_rate_limit` ("you can only
  request this after 59 seconds"). `friendlyAuthError` matched `rate limit`/`over_email` and reported that as
  **"E-mail codes aren't going out right now… ask your administrator"** — so a person who pressed "send a new
  code" twice was told the mail server was broken when it was working fine. The cooldown is now recognised
  first, and says how many seconds to wait; a genuine send failure no longer sends anyone to an administrator,
  it just asks them to try again.
- **Sign-in codes: people could not enter the code they were sent (2026-10-17):** "E-mail me a code" sends an
  **8-digit** code — that is Supabase's OTP length — but the login form demanded exactly 6 (`pattern="\d{6}"`,
  `maxLength={6}`, and a button disabled until `code.length === 6`). The last two digits could not be typed, the
  form failed native validation, and the button never enabled, so anybody signing in with a code was stuck. The
  field now accepts 6–8 digits and enables once there are at least 6, which covers e-mail (8), text (6) and
  whatever the project's OTP setting is changed to later; the label and the confirmation messages no longer claim
  a length. The authenticator-app (TOTP) field stays at 6 digits, which is correct for TOTP.
- **A signature is never refused (2026-10-17, PLAN AGR-04, AGR-05):** signing the MSA between Velocity Workforce
  and DREP Software failed with *"There is already an active MSA between these two companies (MSA-DREPSOFTWARE-001)"*.
  DREP had signed; Velocity's administrator was the second signer and got the error. The real story:
  - Velocity had raised a counter-MSA while DREP's was `out_for_signature`. The one-live-MSA-per-pair trigger only
    counts `pending` / `accepted` / `active` as live, so an unsigned copy did not stop a second one being created,
    and the pair ended up with two MSAs waiting on each other.
  - When the last signer finished, sealing the envelope set the agreement to `accepted`. That is an `UPDATE`, so
    the same trigger fired, found Velocity's pending MSA and raised — **aborting the whole transaction**. The
    signature had been recorded in the audit trail and was legally real, yet the request returned a conflict and
    the signer was told to try again.
  - Now the rule guards *creating* a second live MSA, which is where duplicates actually come from; a status
    change on an agreement that already exists never raises. When an MSA comes into force, the opposite-direction
    agreement for the same pair that has **not** come into force is superseded (with a note naming its
    replacement) rather than left dangling. An MSA already in force is never quietly ended by someone else's
    signature — and if legacy data somehow has two in force, a signature still goes through.
  - Migration `20261016001800`.
- **SOWs run both ways under one MSA, sent to the other company for approval (2026-10-17, PLAN AGR-05):**
  - **Either company can raise work under an MSA, whichever workspace recorded it.** `POST /sows` read the
    agreement with a plain `SELECT`, and the restrictive tenant-isolation policy hides another workspace's
    agreement rows — so the company an MSA was *sent to* got a 404 for an MSA they could plainly see in
    `GET /agreements`. Work under one MSA now runs from whichever side you are on.
  - **A SOW points at the right company.** It used to copy `company_id` off the agreement, which seen from the
    counterparty's side is *their own* company, so a reverse-direction SOW would have pointed back at the sender
    of the MSA. `mytrakin.agreement_peer_company()` resolves the other party from wherever you stand.
  - **Sent for approval, like an MSA.** `draft` → `pending` (sent) → `active` (approved) or `rejected` with a
    reason kept on the row. `POST /sows/{id}/submit`, `POST /sows/{id}/respond`. Turning one down needs a reason;
    the company that raised it cannot answer its own SOW; an unrelated workspace neither sees nor can answer it.
  - **A draft stays private.** An unsent SOW is the other company's work in progress and does not appear at all.
    Once sent it is shared read-only and **without money** — reference, title, term and status only. Value
    ceiling, invoiced, paid, burn and amendments never leave the workspace that created them.
  - Migration `20261016001700`.
- **Find anybody on the platform when onboarding a consultant, and show your U-ID on your profile (2026-10-17, PLAN
  CON-02, U-ID):**
  - **The picker searches every registered myTrakIn user, not only your own workspace.** It previously listed just
    the people already linked to your workspace (members, plus people added to your companies), so searching for a
    colleague who has an account but has never worked with you returned "Nobody matches". `GET /consultants/candidates`
    now matches on name, U-ID or e-mail across the platform and marks each result `new to this workspace` where
    they have no access here yet. Only id, U-ID, name, e-mail and mobile are returned — never anything else from a
    profile that is not yours — and a search term of two characters or more is required, so it cannot be used to
    page through the whole user list.
  - **Onboarding somebody who is new to your workspace now actually works.** Giving them access meant inserting a
    membership, and `memberships` is tenant-admin-only under row-level security, so HR, account managers and legal
    could never do it — only an owner could, by hand. `mytrakin.grant_consultant_access()` (migration
    `20261016001600`) is the narrow way in: it may create a *consultant* membership, or attach the consultant link
    to somebody who is already a member here, keeping the role they have. It cannot change anybody's role or status.
  - **A person's U-ID is shown on their profile.** `/network/me` and `/network/people/{id}` return `user_code`, and
    both the "My profile" page and any colleague's profile now show it under the name. It was in the users list, the
    consultant list and the consultant record, but missing from the profile itself.
- **Onboarding a consultant: pick the person, don't type them (2026-10-17, PLAN CON-02):** the free-text "Full name"
  box is gone. Search the people registered with your workspace by name, U-ID or e-mail; each result shows the U-ID,
  and anyone already on the books here is marked as such. Choosing someone fills in the e-mail and mobile, and the
  API reads the name, e-mail and mobile from that person's profile rather than trusting the form, so a consultant
  can no longer be created as a near-duplicate of somebody already here under a different spelling. The same person
  cannot be onboarded twice. A consultant must already have a myTrakIn account. Fixed alongside it: onboarding
  someone who already had a role in your workspace used to leave them on that role with no consultant access,
  because `memberships` is unique per (tenant, user) - the link is now attached without taking their access away.
- **Send for signature: pick your signers, attach a packet, tell the other company (2026-10-17, PLAN ESG-02, NOT-02):**
  - **Signers are chosen, not typed.** "Send for signature" asks who is expected to sign: you are fixed as the
    first signer (your own company), and the second is picked from the other company's own admins and owners —
    only people who may actually sign for them, strongest role first. When that company has no admin with an
    account yet, the form falls back to inviting the signer by e-mail instead of blocking the send.
    `GET /envelopes/signing-parties`.
  - **Several documents per envelope.** An MSA and its SOW, or a contract and its exhibits, now travel as one
    envelope: add documents up front or to a draft later, and every signer gets them in order followed by one
    certificate of completion. `POST /envelopes/{id}/documents`, `DELETE /envelopes/{id}/documents/{id}`,
    migration `20261016001400`.
  - **The other company is told.** Sending e-mails every admin of the counterparty company, not just the signer —
    the agreement is theirs to action even when they are not the one signing. It is recorded on the envelope's
    timeline as "Counterparty notified" and listed in the notification log. (They also already see the agreement
    in their own workspace, read-only.)
  - The form field is now labelled **Note** rather than "Message to signers".
- **Company profiles are private to their workspace again (2026-10-17, PLAN RULE-01, SEC-13, CO-03):** the
  cross-tenant company directory had left behind a row-level-security policy that let **any signed-in person read
  every company row in every workspace** — contact e-mail, address, EIN, W-9 status and data, notes, bank_verified.
  Opening another workspace's company returned 200 with its details. The directory needs only names, so it now goes
  through the narrow `company_directory_all()` / `company_public_name()` / `company_counterparty()` helpers and the
  broad policy is dropped; a company outside your workspace is 404, not a redacted 200. Migration
  `20261016001300`. The MSA picker still lists every active company, and an agreement with a company of another
  workspace still shows who it is with.
- **Green CI (2026-10-17):** the three tests that had been failing on every push since 2026-10-16 are fixed, and the
  cross-tenant company read is now covered by a regression test.
  - The agreement **list** resolves a cross-tenant counterparty's name through `company_public_name()`, like the
    agreement detail and SOW list already did — an MSA with another workspace's company showed a blank counterparty.
  - A company admin asking for an MSA **from a company they cannot read** now gets 404 instead of 403: a workspace
    you can't see must be indistinguishable from one that doesn't exist.
  - `test_non_staff_can_upload_session_w9` uses its own EIN; it had been reusing the shared fixture EIN that another
    test in the same workspace already registered.
- **MSA lifecycle between two companies (2026-10-16, PLAN AGR-07):**
  - An MSA sent from company A to company B is `pending` until B answers. B accepts → `accepted` (in force); B rejects
    with a note → `rejected` (the note is shown to A). Recording a paper or e-signed acceptance also accepts it.
  - Only one live MSA (pending, accepted or legacy active) can exist between two companies, whichever way round it was sent.
  - MSAs past their end date move to `expired` in the daily job. Billing and project gates count only accepted (or legacy
    active) MSAs, so a pending or expired one doesn't unlock them.
  - Renewals: either company requests a renewal with a new end date and a note. The other accepts (the end date moves;
    an expired MSA becomes accepted again) or declines with a note.
  - Migrations `20261016001500` (lifecycle) and `20261016001501` (fix to the answer functions).
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
