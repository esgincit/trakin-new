# myTrakIn — complete requirements & delivery plan

Status: 2026-10-13 · Keep this file current: when an item ships, change its status and add the PR/commit.

**Three documents, read in this order:**
1. **This file** — requirement IDs, status (built / partly / not built) and the work order.
2. [prototype-spec.md](prototype-spec.md) — the full written spec of every screen, field, button, message, formula,
   list and constant in the prototype. Section tags like `[AR]` match the ID prefixes here. **Before building any
   item, read its section there.**
3. [prototype/mytrakin-prototype.html](prototype/mytrakin-prototype.html) — the customer's original clickable
   prototype (open in a browser, switch "Demo role"). The final word when the spec is unclear.
Business rules as built are in [functional.md](functional.md).

---

## 0. How to use this document

- Every requirement has an ID (`AUTH-03`, `AP-07` …). Use the ID in branch names, commits and PRs
  (`feat/AP-07-nacha-file`, `AP-07: NACHA file for payment runs`).
- **Status** — ✅ done in code · 🟡 partly done (the note says what is missing) · ❌ not built.
  Statuses come from reading the code (routes, tables, pages) on 2026-10-13, not from click-testing. Phase 0
  confirms every ✅ by hand; downgrade anything that fails.
- **Work order** is §7 (backlog). Pick the top open item, finish it, tick it, take the next.
- **Definition of done** for every item:
  1. Works for every role listed in §3 for that screen, and *hides* what other roles must not see.
  2. API endpoint has a test in `apps/api/tests`; RLS policy for any new table.
  3. Every write lands in the audit log (DB trigger — don't bypass).
  4. Lists have search, filters, sort, list/cards and CSV export (use `DataTable`).
  5. Works on a phone (no horizontal scroll) and in dark mode.
  6. `make check` green; user manual / functional spec updated; CHANGELOG line.

---

## 1. Product goal

US IT staffing companies sit in the middle of a vendor chain:

```
End client → Prime vendor → Staffing company (tenant) → C2C vendor / 1099 contractor / W-2 employee → Consultant
```

myTrakIn tells the staffing company, for every consultant and billing period: **who owes us, whom do we owe, where is
the money stuck, and are the contracts, hours and documents behind it in order.** It is a multi-tenant SaaS: each
staffing company is a workspace (tenant); the platform owner runs the SaaS.

### Non-negotiable rules
| ID | Rule |
|---|---|
| RULE-01 | **AR/AP only.** A tenant stores only its two links: bill rate to its customer (AR) and pay rate to its vendor/contractor (AP). Links it is not party to are shown by name with `••••` and never stored (rate column is null). |
| RULE-02 | Amounts are role-scoped (see §3.2). Vendors never see client amounts; consultants never see any amounts. |
| RULE-03 | Nothing is deleted: inactive companies, former consultants, voided invoices and removed files are kept (files 30 days in trash; records for the retention period). |
| RULE-04 | Every change, sign-in, approval, export and file action is audited (who, when, IP, device, before/after). |
| RULE-05 | Platform staff cannot see tenant data except through time-boxed, tenant-approved support access. **Amended 2026-10-15 (owner):** the platform admin may see the onboarding record (company details, W-9 fields and file, verification checks) of a company **waiting for activation**, and per-company money **totals** (invoiced / collected / billed / paid) — never individual invoices or rates. |
| RULE-06 | Sensitive data (SSN, bank account numbers) is never accepted in CSV or free text — only on W-9 / bank forms. |
| RULE-07 | **Nothing is copied or implemented from the old Contrack project** (owner's instruction). Only its service settings (Zoho SMTP) and security/engineering lessons are used — see [legacy-contrack.md](legacy-contrack.md). A feature that is not in the prototype is not built. **Amended 2026-10-15:** the owner's e-mail "MyTrakin implementation master specification" ([requirements/2026-10-15-mail-master-spec.md](requirements/2026-10-15-mail-master-spec.md)) is also a requirement source and **wins over the prototype where they differ** (§5.30). |

---

## 2. Roles

| Role | Who | Home screen |
|---|---|---|
| Platform owner | Company running myTrakIn | Platform dashboard |
| Tenant admin | Owner/COO/technical lead of the staffing company | Dashboard |
| Finance (AR/AP) | Controller, AP/AR specialist | Dashboard |
| Account manager | Sales/delivery, scoped to assigned clients | Dashboard |
| Contracts / legal | Contracts manager, signatory up to a limit | Dashboard |
| HR & compliance | Onboarding, I-9, documents | Dashboard |
| Approver | Delivery manager (timesheets) | Timesheets |
| Viewer | Leadership, auditors (read-only, no rates/AP) | Dashboard |
| Vendor admin | C2C vendor's account manager | Vendor home ("My payments") |
| Client user | Customer contact | Partner home |
| Consultant | W-2, C2C or 1099 worker | My payments & documents |

---

## 3. Access

### 3.1 Menu by role (from the prototype)
| Screen | Platform | Admin | Finance | AM | Legal | Vendor | Consultant |
|---|---|---|---|---|---|---|---|
| Dashboard | | ✓ | ✓ | ✓ | ✓ | ✓ (vendor view) | |
| My approvals | | ✓ | ✓ | ✓ | ✓ | | |
| Reports | | ✓ | ✓ | ✓ | | | |
| My payments & documents | | | | | | | ✓ |
| Onboarding pipeline | | ✓ | | ✓ | ✓ | | |
| Consultant onboarding | | ✓ | | ✓ | ✓ | | |
| Registrations | | ✓ | | | ✓ | | |
| MSA, SOW & agreements | | ✓ | ✓ | ✓ | ✓ | ✓ (own) | |
| E-signatures | | ✓ | ✓ | ✓ | ✓ | ✓ (own) | (via link) |
| Projects | | ✓ | ✓ | ✓ | | | |
| Placements & chain | | ✓ | ✓ | ✓ | | ✓ (own) | |
| Timesheets | | ✓ approve | ✓ view | ✓ view | | ✓ own consultants, view | ✓ own |
| Payment flow | | ✓ | ✓ | ✓ | | | |
| Invoices & reminders | | ✓ | ✓ | ✓ | | | |
| Client receipts (AR) | | ✓ | ✓ | ✓ | | | |
| Vendor payouts (AP) | | ✓ | ✓ | | | ✓ "My payments" | |
| 1099 contractors / W-2 payroll / Referral payouts | | ✓ | ✓ | | | | |
| Payment ledger | | ✓ | ✓ | | | ✓ own | |
| Consultants & work auth | | ✓ | | ✓ | ✓ | | |
| Clients & vendors | | ✓ | ✓ | ✓ | ✓ | | |
| Compliance / Document expiry | | ✓ | | ✓ (expiry) | ✓ | ✓ own | |
| Network & messages | | ✓ | | ✓ | ✓ | ✓ | ✓ |
| Users & security, Approvals & hierarchy | | ✓ | | | (users: view) | | |
| Audit log | | ✓ | ✓ | | ✓ | | |
| Data import & export | | ✓ | ✓ | | | | |
| My profile & settings | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Platform dashboard, Tenants, Sign-up approvals, Plans & billing, Support & audit log | ✓ | | | | | | |

The product has more roles than the prototype (HR, approver, viewer, client); map them as: HR ≈ legal's compliance
screens + consultants; approver ≈ timesheets + My approvals; viewer ≈ read-only finance without AP/rates; client ≈
own invoices and projects.

### 3.2 Permission matrix (prototype "Access matrix")
| Action | Admin | Legal | Finance | Acct mgr | Vendor | Consultant |
|---|---|---|---|---|---|---|
| View MSA | ✓ | ✓ | ✓ | scoped | scoped | — |
| View SOW / WO | ✓ | ✓ | ✓ | scoped | scoped | scoped (dates only) |
| View SOW value and rates | ✓ | ✓ | ✓ | scoped (AR side) | scoped (own link) | — |
| Record client payment | ✓ | — | ✓ | — | — | — |
| Approve vendor payment run | ✓ | — | ✓ | — | — | — |
| See vendor payable amounts | ✓ | — | ✓ | — | own | — |
| Create / edit SOW draft | ✓ | ✓ | — | scoped | — | — |
| Sign (e-signature) | within limit | within limit | — | — | own company | own documents |
| Amend / terminate | ✓ | ✓ | — | scoped | — | — |

*Scoped* = assigned clients only (AM), own company and own link only (vendor), or a signing-authority dollar limit.

| ID | Requirement | Status |
|---|---|---|
| ACC-01 | Menus and API both enforce §3.1; a hidden screen's API returns 403. | ✅ |
| ACC-02 | Amount visibility per RULE-02 on every screen and export (masked `••••`). | ✅ verify per screen in Phase 0 |
| ACC-03 | **Account-manager scope**: AM sees only assigned clients (and their SOWs, invoices, projects). Needs a scope list on membership. | ❌ |
| ACC-04 | Access-matrix tab (read-only table of §3.2) in Agreements and in Users & security. | ❌ |
| ACC-05 | Signing limit enforced: a signatory can only countersign envelopes up to their `signing_limit`. | ❌ (field stored, not enforced) |

---

## 4. Cross-cutting requirements (every screen)

| ID | Requirement | Status |
|---|---|---|
| UX-01 | App shell: left nav grouped by section, with **badge counts** (approvals waiting, pending registrations, docs ≤30 days, envelopes to sign, starts ≤14 days). Workspace switcher. | 🟡 nav done; badges missing |
| UX-02 | **Global search** in header: invoices, SOWs, MSAs, consultants, projects, companies (platform: tenants); results open the record. Hidden for consultants. | ❌ |
| UX-03 | **Notifications bell** with count; drawer lists alerts (approvals, missing/expiring items, stalled tenants, consultant to-dos) each linking to the record. API `GET /notifications` exists. | 🟡 API only |
| UX-04 | **AI assist** button in header: role-scoped suggested next actions + "Ask a question" box + quick prompts; nothing sent or changed without a click. | 🟡 suggestions + ask on dashboard; no header drawer |
| UX-05 | Every table: search, up to 4 column filters, sortable headers, sort menu, clear, row count, list/cards switch, export CSV of what is visible. | ✅ `DataTable` — check every list uses it |
| UX-06 | Record drawers/detail pages with **Files** block: add (virus-scanned, encrypted), download, remove (kept 30 days), list/thumbnail switch. | 🟡 files done; thumbnails + 30-day trash not visible |
| UX-07 | Toasts for every action; confirmation text says what happened (e.g. "BP-INV-1187 released for the next run"). | ✅ verify |
| UX-08 | Light/dark/system theme; compact density; phone layout. | 🟡 density done; theme choice missing |
| UX-09 | Account menu under avatar: profile, account & security, notifications, preferences, privacy, sign out. | ✅ partial — check items |
| UX-10 | "Sample template / Import / Export" toolbar on every page that has importable data (consultants, companies, projects, placements, SOWs, timesheets, AR, AP, payments, users). | 🟡 central `/data` page done; per-page toolbar missing |

---

## 5. Module requirements

### 5.1 Public: sign-in (`/login`)
| ID | Requirement | Status |
|---|---|---|
| AUTH-01 | Methods: SSO (SAML/OIDC: Entra ID, Okta, Google Workspace), e-mail one-time code, SMS code, Google, Microsoft. | ✅ code · ⏳ Google + Microsoft need provider keys switched on in Supabase — see [auth-setup.md](auth-setup.md) |
| AUTH-02 | **Passkeys** (WebAuthn: Face ID, Touch ID, Windows Hello, security key) as sign-in and as second factor. | ❌ |
| AUTH-03 | 6-digit code, 10-minute expiry, 5 attempts then 15-minute lock; locked users visible to admin with Unlock. | 🟡 verify Supabase settings + unlock action |
| AUTH-04 | Second factor required for admin, finance and approvers (authenticator or passkey; SMS not accepted for these roles). | ✅ (TOTP) |
| AUTH-05 | Passwords off by default; when on: 12+ chars, letters+numbers, breached-password check, change signs out other sessions + confirmation e-mail. | 🟡 verify breach check + email |
| AUTH-06 | SSO redirect when the e-mail domain is verified for a tenant. | 🟡 verify |
| AUTH-07 | **Re-authenticate** before payments, bank-detail changes and exports (setting: all three / payments only). | ❌ |
| AUTH-08 | Optional: restrict admin sign-in to office/VPN IP ranges. | ❌ |
| AUTH-09 | Session idle timeout setting (30 min / 8 h / 12 h). | ✅ |
| AUTH-10 | Sign-in history with IP, approximate location, device, result; block + alert on new country without MFA. | ❌ |
| AUTH-11 | **Forgot password:** "Forgot password?" on the password step → e-mailed one-time link → `/reset-password` (new password 12+ chars, letters + numbers) → authenticator code if enrolled → app. Identical message whether or not the account exists. | ✅ (2026-10-13, branch `feat/AUTH-login-mfa-social`) |
| AUTH-13 | **New user with no workspace:** signing in with Google/Microsoft/e-mail creates the account automatically (Supabase) and opens the **Network feed** — no "request a workspace" wall. Limited menu: Network (feed, people, messages), My businesses, My profile, Account & security (where two-step verification is set up). Workspace-only pages redirect to the feed; posts default to "Everyone in my network". API: network endpoints use `member_db` (person-only when there is no workspace); no database change. | ✅ (2026-10-14, branch `feat/AUTH-no-workspace-home`; API test added, runs in CI) |
| AUTH-12 | **Social sign-in UX:** Google/Microsoft buttons on sign-in and create-account, with brand marks; a button is hidden when Supabase reports its provider switched off; provider errors (cancelled, not enabled, redirect not allowed, bad key) shown in plain words; "Cancel and sign out" from the two-step screen. | ✅ (same branch) |

### 5.2 Public: registration (`/register/[tenantId]`, `/signup`)
| ID | Requirement | Status |
|---|---|---|
| REG-01 | Wizard: who you are → verify e-mail by code → details → documents → review & submit → reference number. | 🟡 verify code-verification step and stepper |
| REG-02 | Types: staffing company (own workspace, approved by platform), vendor, client, 1099 contractor, consultant. | ✅ |
| REG-03 | Required documents per type (tenant: incorporation, EIN letter CP 575/147C, signatory ID; vendor: formation, W-9, COI, bank letter; client: W-9, AP contact sheet; 1099: W-9, resume, liability insurance optional; consultant: resume, photo ID). | 🟡 verify list matches |
| REG-04 | Accept Terms, Privacy; consultants/1099 e-sign mutual NDA; vendors accept Vendor Code of Conduct. | ❌ verify |
| REG-05 | Automatic checks shown to approver: e-mail verified, business domain (free domains flagged), EIN present, duplicates. | ✅ |
| REG-06 | External checks: IRS TIN match, Secretary of State status, OFAC sanctions screen, bank account verification. | ❌ needs provider decision (D5) |
| REG-07 | Taxpayer ID only on the W-9, never in free text. | ✅ verify |

### 5.3 SaaS platform (owner console, `/platform`)
| ID | Requirement | Status |
|---|---|---|
| PLAT-01 | Dashboard KPIs: tenants (+added this month), live %, in onboarding (stalled / not activated), MRR + ARR, avg days to go live, revenue per user (paid seats, payments tracked 30 d). | 🟡 missing avg time-to-live, payments tracked |
| PLAT-02 | Charts: tenants added vs went live per month; onboarding funnel (8 steps) with "biggest drop" sentence. | ❌ |
| PLAT-03 | Lists: onboarding in progress (status, progress n/8, next step, last active); revenue by plan; recent platform activity. | 🟡 verify |
| PLAT-04 | Tenant statuses: Live, Onboarding, Invited, Stalled (no activity 14 days), Suspended. Filters with counts, search, export. | 🟡 verify "Invited"/"Stalled" |
| PLAT-05 | Tenant onboarding steps (8): created → admin invited → admin activated (MFA) → company profile → clients & vendors → MSAs/SOWs → first invoice → first payment (live). | 🟡 product uses a different 8-step list (functional §3.2) — align (D6) |
| PLAT-06 | Tenant detail: admin, created/live dates, subscription, usage, checklist; actions resend invite, send check-in, suspend (users read-only) / reactivate, request support access. | 🟡 support access + check-in missing |
| PLAT-07 | Add tenant: legal name, EIN, state, admin name/e-mail, plan, trial toggle, **modules** (payments, MSA & SOW, timesheets, vendor portal, community). | 🟡 modules missing |
| PLAT-08 | Sign-up approvals: verification checks + documents, flag (e.g. free e-mail), request info / reject / approve & create tenant. | ✅ (checks limited — see REG-06) |
| PLAT-09 | **Plans & billing**: plan cards (price/user, minimum seats, features, tenants, MRR); KPIs MRR, paid seats, ARPU, revenue per tenant; monthly subscription invoices per tenant (users, billed seats, amount, paid/due/overdue). External users free. | ❌ (D1 pricing) |
| PLAT-10 | Auto-suspend after 60+ days unpaid; data kept read-only. | ❌ |
| PLAT-11 | **Support access**: platform staff request 30-min access with reason → tenant admin approves → time-boxed → logged in Support & audit log and tenant audit log. | ❌ |
| PLAT-12 | Platform "Support & audit log": every platform action and support access. | 🟡 verify platform actions are logged |

### 5.4 Workspace setup & settings (`/settings`)
| ID | Requirement | Status |
|---|---|---|
| SET-01 | Company details (legal name, EIN, state), invoice footer. | ✅ |
| SET-02 | Allowed sign-in methods, MFA for all staff, idle sign-out. | ✅ |
| SET-03 | Setup checklist (8 steps) with go-live. | ✅ |
| SET-04 | SSO & provisioning tab: IdP, verified domains (DNS TXT), enforcement, break-glass account, test connection; SCIM with group → role mapping. | ❌ SCIM is Phase 3 |
| SET-05 | 1099-NEC threshold override per year. | ✅ verify |

### 5.5 Dashboard (`/dashboard`)
| ID | Requirement | Status |
|---|---|---|
| DASH-01 | KPIs: receivable outstanding, overdue from clients (oldest days late), collected 30 d, payable to vendors*, held vendor payments*, MSA/SOW expiring (SOW ≤60 d, MSA ≤90 d). *finance/admin only, masked otherwise. | ✅ |
| DASH-02 | Expected cash in vs out, next 6 weeks + past due. Vendor dates = scheduled run, or for pay-when-paid client due date + 3 days; exceptions excluded. | ✅ verify rule |
| DASH-03 | Needs attention: overdue AR, AP exceptions, held, SOW ≥90 % burn, MSA expiring ≤90 d. | ✅ |
| DASH-04 | Smart suggestions card (top 4) + "See all & ask". | ✅ |
| DASH-05 | Missing & expiring card (agreements, documents, policies, work auth, timesheets). | ✅ |
| DASH-06 | Open payment flows (top 4) with link to Payment flow. | 🟡 verify |
| DASH-07 | Vendor dashboard: invoiced to tenant, paid, waiting on client (pay-when-paid), next expected payment, their invoices. | ✅ `/partner` verify |

### 5.6 My approvals & hierarchy
| ID | Requirement | Status |
|---|---|---|
| APR-01 | **My approvals inbox**: one table of items waiting on me — type, reference, detail, requested by, current step, amount; Approve / Reject inline; nav badge. Types: timesheet, expense, time off, vendor-invoice exception, SOW amendment, payment run, bank-detail change, rate change, registration, referral fee. | ❌ |
| APR-02 | Approving in the inbox does the same as approving on the record (e.g. exception accepted at approved hours, registration approved). | ❌ |
| APR-03 | **Approval chains** (configurable per tenant, defaults): Timesheet: consultant → admin. AR invoice: from approved time → finance review → sent. AP invoice: AP specialist (3-way match) → finance manager ≤ $25k → admin above. Payment run: finance manager → admin (dual above $25k). SOW/amendment: AM → legal → finance (if margin < 15 %) → signatory. MSA/ICA/offer: legal → admin → e-signature. Bank change: requester → finance manager + phone callback. Registration: compliance → admin. Referral fee: finance manager → admin above $2,500. Rate change: AM → finance manager. | ❌ |
| APR-04 | **Bank-detail change** flow: request (masked old → new), second approver + recorded phone callback to a contact already on file; payouts to that payee paused until approved. | ❌ |
| APR-05 | **Rate change** request (vendor rate from date, shows new margin) routed for approval; applies only to un-invoiced time. | 🟡 finance can change rates directly; no request/approval |
| APR-06 | **Org chart** from reporting lines (`manager_id`). | ❌ |
| APR-07 | **Delegation**: from → to, date range, scope (e.g. all finance approvals); shown as Scheduled/Active; audited. | ❌ |

### 5.7 Reports (`/reports`)
| ID | Requirement | Status |
|---|---|---|
| RPT-01 | Reports hub, role-filtered: AR aging, AP aging & payment run, cash forecast, margin by placement, timesheet compliance, hours by consultant & project, SOW burn & expiry, MSA & agreement expiry, 1099 summary, payroll register, referral fees, work authorization, onboarding status, audit trail. Each: Open (filtered live list) + Export CSV. | ❌ |
| RPT-02 | Period picker (this month, last month, QTD, YTD, custom) and customer filter. | ❌ |
| RPT-03 | Schedule a monthly report pack by e-mail. | ❌ |

### 5.8 Onboarding pipeline & registrations
| ID | Requirement | Status |
|---|---|---|
| ONB-01 | **Pipeline board**: every client, vendor, 1099 and consultant against 8 stages (Registered → Verified → MSA/ICA/offer → SOW/work order → Digitally signed → Project set up → Timesheets live → Invoicing live) with blocker text; KPIs in onboarding / live / blocked / new registrations. | 🟡 company stages exist; no combined board |
| ONB-02 | Party detail: checklist n/8, blocker, send reminder. | 🟡 |
| ONB-03 | **Invite to onboard**: type, name, e-mail, mobile → secure personal link; shows "Invite sent — waiting for registration". | 🟡 public link exists; personal invite missing |
| ONB-04 | Registrations list: checks + documents chips, Request info (e-mail), Reject, Approve / Approve anyway. Approval creates company at stage 2 with next step (MSA / ICA / offer+NDA) and moves files. | ✅ |
| ONB-05 | Preview public registration page. | ✅ |

### 5.9 Consultant onboarding (`/consultants`)
| ID | Requirement | Status |
|---|---|---|
| CON-01 | Engagement types and checklists: W-2 full-time, W-2 contract, C2C, 1099 (lists in functional §3.4). | ✅ |
| CON-02 | Onboard form: type, employer (C2C), name, e-mail (personal ok), mobile, title, start date, location, **any number of projects** each with hours/week, AR bill rate, AP/pay rate. | 🟡 identity is picked, not typed (2026-10-17): search **every registered myTrakIn user** by name/U-ID/e-mail (they need not be linked to your workspace yet), their details come from their profile, and the same person cannot be onboarded twice; multi-project rows still to verify |
| CON-03 | List: progress n/N, next step, starting in 14 days, ready to activate; filter by type. | ✅ |
| CON-04 | Activate only when checklist done (project item may be open); creates placements and timesheet access; sends sign-in invite. | ✅ |
| CON-05 | Rehire from Former: restarts checklist. | ✅ |

### 5.10 Consultants & work authorization
| ID | Requirement | Status |
|---|---|---|
| WA-01 | List: type, projects, work-auth type, valid until (days, colour), I-9, E-Verify, NDA. KPIs: consultants by type, expiring ≤120 d, missing agreements. | ✅ |
| WA-02 | Detail: employer, projects, skills, compliance block, agreements & policies, files (HR/compliance/admin only), Message. | ✅ |
| WA-03 | I-9/E-Verify only after offer accepted; C2C = employer attests; 1099 = no I-9; reminders 120/90/60/30 days. | ✅ |
| WA-04 | Offboard: last day, reason, rehire eligible, **offboarding checklist** (final timesheet, final invoice/payable, client & vendor notified, access revoked, equipment returned, NDA exit acknowledgment). | 🟡 checklist missing |
| WA-05 | Former tab: KPIs (former, eligible for rehire, left in 6 months, W-2 I-9s kept); **records kept until** date (I-9: later of hire+3 y / end+1 y; others end+7 y). | 🟡 retention dates missing |
| WA-06 | Former consultants can't sign in. | ✅ |

### 5.11 Agreements: MSAs, SOWs, policies (`/contracts`)
| ID | Requirement | Status |
|---|---|---|
| AGR-01 | KPIs: active MSAs (expiring ≤90 d), active SOWs (ending ≤60 d), SOWs ≥90 % burn, supplier-side value remaining. | ✅ verify |
| AGR-02 | SOW table: we bill / we pay filter, value, invoiced, collected/paid, remaining, burn bar (≥75 % warn, ≥90 % bad), status; values masked by role. | ✅ |
| AGR-03 | MSA table: kind, counterparty, we are supplier/buyer, effective, expiry (days), terms, renewal, notice, insurance, SOW count/value. | ✅ |
| AGR-04 | SOW detail: flows-down-from / flows-down-to, warnings (runs past upstream; downstream ends first), amendment, invoices under SOW, signed copy, e-signature section. | ✅ verify warnings |
| AGR-05 | MSA detail: SOWs under it, expiry warning ("new SOWs and payments blocked after expiry"), Start renewal. | 🟡 renewal action + blocking rule verify; two-way SOWs under one MSA with send-for-approval and approve/turn-down shipped 2026-10-17 |
| AGR-06 | Tabs: offer letters & NDAs per consultant; policy acceptance matrix (consultant × policy); missing checklist with Remind. | ✅ verify tabs |
| AGR-07 | Add existing MSA/SOW (already signed) with PDF; import MSAs/SOWs; templates. | ✅ |
| AGR-08 | Amendments: draft → send for signature → applied automatically when signed. | ✅ |
| AGR-09 | Block: invoices/payments for a company with no active MSA; new SOWs after MSA expiry. | ✅ built 2026-10-15 on `feat/wf-workflow` — API tests written, **not yet run in CI** |
| AGR-10 | Expiry e-mails to legal at 90/60/30 days. | ✅ |

### 5.12 E-signatures (`/esign`, `/sign/[token]`)
| ID | Requirement | Status |
|---|---|---|
| ESG-01 | Tabs: action required, waiting, completed, drafts, all; KPIs needs your signature, waiting on others, completed, avg days to sign. | ✅ verify KPIs |
| ESG-02 | Send: pick MSA/SOW/amendment or **template (Mutual NDA, offer letter W-2, ICA 1099)** or upload PDF; title; signers in order; expiry days; remind every N days; message; save draft or send. | 🟡 signers now picked from each company's own admins (creator fixed first, e-mail fallback), several PDFs per envelope, every admin of the counterparty notified on send; **templates missing** |
| ESG-03 | Signer flow: e-mail code → ESIGN/UETA consent → read → type or draw signature + intent checkbox → sign; or decline with reason. | ✅ |
| ESG-04 | Evidence per event: UTC time, IP, device, approximate location, auth method. | ✅ |
| ESG-05 | Completion: sealed PDF + certificate of completion, SHA-256; all parties e-mailed; record updated (amendment applied, MSA renewed, NDA marked signed). | ✅ |
| ESG-06 | Remind, void (reason), download any time; envelope detail with per-signer timeline. | ✅ |
| ESG-07 | Countersigner choice limited by signing authority (ACC-05). | ❌ |
| ESG-08 | Template version on send: current approved template, or custom (requires legal approval before sending). | ❌ |

### 5.13 Projects & placements (`/projects`)
| ID | Requirement | Status |
|---|---|---|
| PRJ-01 | Project: code, name, client, prime (if sub), dates, tenant manager, client timesheet approver, description, linked SOWs, team (role, engagement, allocation), this week's timesheet status, files; invoiced of value (finance). | ✅ |
| PRJ-02 | Placement: consultant, project, role, dates, hours/week, end client (name only), AR customer + SOW + bill rate + terms, AP payee + SOW + pay rate + terms + pay-when-paid. W-2 has no AP payee. | ✅ |
| PRJ-03 | **Chain diagram** per placement: End client (••••, "not our contract") → Customer → AR rate/doc/terms → Us → AP rate/doc/terms → Vendor/1099 → Consultant (or W-2 payroll). | 🟡 verify diagram exists |
| PRJ-04 | Rate changes: finance only, audited, apply to un-invoiced time. | ✅ |

### 5.14 Timesheets (`/timesheets`, `/my/timesheet`)
| ID | Requirement | Status |
|---|---|---|
| TS-01 | One timesheet per consultant per week (Sun–Sat), rows per project + internal; add/remove project rows; 0–24 h per day. | ✅ |
| TS-02 | Save draft, submit; submitted/approved weeks locked; returned with reason shown to consultant. | ✅ |
| TS-03 | Checks: submitted, no day >12 h, within allocation, weekend hours, W-2 overtime >40 h, inside placement dates, fits remaining SOW value. | ✅ |
| TS-04 | Approver list per week: KPIs waiting / approved / not submitted / flagged; daily hours; checks summary; approve; **approve all that pass**; **remind not submitted**. | 🟡 browser QA 2026-10-19: no KPIs and no "Remind not submitted" (API or UI); approve-all works |
| TS-05 | Detail shows "what approval creates": AR amount and AP amount (finance/admin). | ✅ |
| TS-06 | All-weeks history for every consultant/project with filters and CSV. | ✅ verify |
| TS-07 | **Adjustment after approval**: request adjustment → re-approval; adjusts un-invoiced amounts or creates a correction line. | ✅ re-open until invoiced; after that a credit note (AR-06) or extra invoice (2026-10-18) |
| TS-08 | Reminders Fri 3 pm, Mon 9 am, escalate Tue (HR/vendor admin). | ✅ |
| TS-09 | Vendors see their consultants' timesheets read-only. | ✅ |
| TS-10 | Approved time off pre-filled on the timesheet; client approver notified. | 🟡 shown on My timesheet (2026-10-18); client approver not notified (no approver e-mail on projects) |

### 5.15 Payment flow (`/payments`)
| ID | Requirement | Status |
|---|---|---|
| FLOW-01 | One row per placement × period: hop cards (end client masked, AR, AP or W-2 payroll), status chip, margin (finance). Filters Open / Needs action / Settled / All with counts; legend. | ✅ |
| FLOW-02 | Detail: billed vs owed, margin % and cash position, timeline (issued, paid, overdue, held, mismatch), actions Record client payment / Open vendor invoice. | ✅ verify timeline |
| FLOW-03 | Statuses: paid, awaiting, due, part paid, overdue (part paid), held, ready to pay, scheduled, exception, W-2 payroll; cycle state: action needed / waiting on customer / in progress / settled. | ✅ |

### 5.16 Invoices & reminders, AR (`/invoices`)
| ID | Requirement | Status |
|---|---|---|
| AR-01 | Create invoices from approved timesheets for a period (one per placement); manual invoice: SOW → rate (read-only) → terms/due from MSA → hours → PO/memo → total; save draft or create & send. | ✅ |
| AR-02 | Tabs: follow-up queue (next automatic reminder, owner, Send now), reminder rules (on/off + channel), reminders sent, all invoices. | 🟡 follow-up queue verify |
| AR-03 | Client receipts: aging buckets (current, 1–30, 31–60, 61–90, 90+), by customer (open, overdue, terms), tabs open / overdue / paid / all / credit notes. | 🟡 aging verify |
| AR-04 | Invoice detail: bill to, consultant/period/hours × rate, SOW/PO, linked vendor bill and its status, payments, collection notes (add), Record payment, Send reminder, **Download PDF**. | 🟡 PDF verify |
| AR-05 | Record payment (amount ≤ balance, date, ACH/wire/check/card/other, reference); part payments; recording releases pay-when-paid AP invoices and says so. | ✅ |
| AR-06 | **Credit notes**: number, customer, against invoice, date, reason, amount, status (open → applied to next payment); reduce balance/aging. | ✅ against one invoice, ≤ its balance (2026-10-18); no void / carry-over yet |
| AR-07 | Reminders: −7 courtesy, +1/+7/+15 (copy AM), +30 escalate finance head + flag stop-work review. | ✅ verify +30 flag |
| AR-08 | **AI-drafted collection e-mail** from invoice, payments and notes; firmer/friendlier; edit and send. | ❌ |
| AR-09 | Void with reason (only without payments). | ✅ |

### 5.17 Vendor payouts, AP
| ID | Requirement | Status |
|---|---|---|
| AP-01 | Vendors submit invoices in portal: number, placement, period, hours; amount = hours × pay rate; upload PDF. | ✅ |
| AP-02 | Three-way match: invoiced vs approved hours vs SOW rate; mismatch → exception; accept at approved hours or return to vendor. | 🟡 "return to vendor" verify |
| AP-03 | Pay-when-paid: held until matching AR paid in full → ready to pay automatically. | ✅ |
| AP-04 | Payment run tab: KPIs ready / held PWP / held exceptions; select eligible invoices, running total; method ACH/wire/check; approve & pay. | ✅ |
| AP-05 | **NACHA (ACH) file** download for the run. | ❌ |
| AP-06 | **Remittance**: preview and e-mail remittance advice to each payee on payment. | ❌ |
| AP-07 | Schedule an invoice for a run date. | ✅ |
| AP-08 | By-vendor tab: invoiced, paid, open, held, MSA expiry chip, compliance chips (COI, W-9); imported pre-myTrakIn payment history. | 🟡 verify |
| AP-09 | Payouts held automatically when vendor COI expired or W-9 missing. | 🟡 verify enforcement |
| AP-10 | Vendor view "My payments": their invoices, expected date, PWP explanation, no client amounts. | ✅ |

### 5.18 Payment ledger
| ID | Requirement | Status |
|---|---|---|
| LED-01 | Every payment in and out, newest first: date, received/paid, counterparty, invoice, consultant, method, reference, ± amount; KPIs received / paid out / net cash; counterparty filter; CSV. Vendor sees own only. API `GET /v1/payments` exists. | ❌ page |

### 5.19 1099 contractors, W-2 payroll, referrals (`/pay`)
| ID | Requirement | Status |
|---|---|---|
| PAY-01 | 1099: payees (contractors + individual referrers), agreement, W-9/TIN status, terms, paid YTD, 1099-NEC will be issued / below threshold; KPIs; contractor invoices table. | ✅ |
| PAY-02 | Payment to a payee without valid W-9 is held or warns about 24 % backup withholding. | 🟡 verify |
| PAY-03 | W-2 payroll register per run (imported/entered): hours, gross, employer taxes, benefits, total cost, net; run tabs; margin per employee incl. bench cost. | ✅ |
| PAY-04 | "Send approved hours to payroll provider" export when hours lock. | ❌ |
| PAY-05 | Referrals: referrer type (individual 1099 / vendor / employee via payroll), hourly fee with cap or one-time after waiting period; accrued, paid, open, status (waiting / payable / blocked W-9 / paid up); Pay. | ✅ |
| PAY-06 | Expenses (consultant submits; approve/reject; finance marks reimbursed; billable flag) and time off (PTO, sick, unpaid; approve/decline). | ✅ |

### 5.20 Clients & vendors (`/companies`)
| ID | Requirement | Status |
|---|---|---|
| CO-01 | Cards/list: name, type, status, contact, state, EIN (finance/admin), agreements, next expiry, open AR/AP; workforce counts for vendors; tabs active / inactive / all. | ✅ |
| CO-02 | Add client/vendor: type, legal name, state, contact e-mail, default terms, invite to vendor portal. | ✅ |
| CO-03 | Detail: agreements (or "No MSA — invoices and payments blocked", Send MSA), compliance documents, billed/owed totals, imported payment history, files, status. | ✅ verify |
| CO-04 | Mark inactive (date, reason; warns about open invoices; users lose sign-in) / reactivate. | ✅ |

### 5.21 Compliance & document expiry (`/compliance`)
| ID | Requirement | Status |
|---|---|---|
| CMP-01 | Compliance list: who, type, requirement, expiry, status, effect (what it blocks). | ✅ |
| CMP-02 | Expiry tracker: I-9 reverification, passport, EAD, I-94/visa, COI, W-9, background check, certification, driver's licence, agreement, other; KPIs ≤30 d, ≤90 d, I-9 due, e-mails sent. | ✅ |
| CMP-03 | E-mails at 120/90/60/30/14/7/0 days then weekly; recipients = person + HR + extra; last/next e-mail columns. | ✅ verify columns |
| CMP-04 | Per-category on/off rules (I-9, passport, EAD/I-94, COI, other); note that passports/green cards are never I-9-reverified. | 🟡 |
| CMP-05 | Detail: schedule, **e-mail preview**, files, mark renewed (new date; updates consultant work-auth for EAD/I-9), send now; "send all due now". | 🟡 preview + send-all verify |
| CMP-06 | Policies: publish version for engagement types (retires previous); acceptance with time, version, IP, device; reminders 0/7/14 days. | ✅ |
| CMP-07 | E-mail log of every message. | ✅ |

### 5.22 Consultant self-service (`/my*`)
| ID | Requirement | Status |
|---|---|---|
| ME-01 | To-do list: sign NDA, accept policies, submit timesheet, upload work-auth renewal. | ✅ |
| ME-02 | Payment status per period **without amounts**: timesheets approved → invoice sent → customer pays tenant → tenant pays you/your employer (held/exception explained) → employer pays you (C2C); W-2: paid via payroll regardless. | ✅ verify wording |
| ME-03 | Projects, chain & SOW: how money flows (names only), assignment dates, days left, governing SOW, pending extension, contacts. | ✅ verify |
| ME-04 | Work authorization: status, valid until, I-9, E-Verify, upload renewal; type-specific text. | ✅ |
| ME-05 | Policies & documents: accept with version/IP/device; signed agreements; company documents (handbook, holidays, expense guide, benefits for W-2). | 🟡 company reference documents verify |
| ME-06 | Timesheet history (filters project/month/status, CSV), expenses (receipt, billable), time off. | ✅ |

### 5.23 Network & messages (`/network`)
| ID | Requirement | Status |
|---|---|---|
| NET-01 | Feed: post (update, kudos, opening, announcement), like. | ✅ |
| NET-02 | **Comments** on posts; **attachments** on posts. | ❌ |
| NET-03 | People: search, connect / connected, message, view profile. | ✅ |
| NET-04 | Messages: threads, unread counts, **file attachment**. | 🟡 attachment missing |
| NET-05 | Profile: photo, cover, headline, location, about, experience, education, certifications, skills, contact, open to work, visibility. | ✅ |
| NET-06 | Skill **endorsements**; **profile strength** meter with to-dos; **people you may know**. | ❌ |
| NET-07 | Profiles opt-in; tenant admin controls who can contact its people; message retention per company policy. | 🟡 verify admin control |

### 5.24 Users, security, account (`/users`, `/account`, `/profile`)
| ID | Requirement | Status |
|---|---|---|
| USR-01 | Users list: role & scope, reports to, sign-in method, second factor, last active, status (active, invited, locked, deactivated), external badge; seats in use (external users free). | 🟡 scope + seat count |
| USR-02 | Invite: name, e-mail, role, scope, reports to, signing limit. | 🟡 scope (ACC-03) |
| USR-03 | Admin user panel: recent sign-ins, active sessions, **send password reset, reset 2-step, sign out everywhere, unlock**, deactivate/reactivate. | 🟡 verify each action |
| USR-04 | One active admin always; admins can't demote themselves. | ✅ |
| USR-05 | Account & security: change e-mail/mobile by code, password, 2-step list (authenticator, passkeys, SMS backup), **recovery codes**, **sessions list with per-device sign-out**, **sign-in activity**, "report it". | 🟡 password, TOTP, sign-out-others done |
| USR-06 | Notifications matrix: events × channels (e-mail, SMS, in-app, push), digest (instant/daily/weekly), quiet hours; security alerts always on. | 🟡 e-mail toggles only |
| USR-07 | Preferences: language, time zone, date format, start page, default list/cards, theme, density. | 🟡 time zone + density only |
| USR-08 | Privacy: profile visibility, who can message, show contact to connections, open to projects; **download my data**; e-records consent / **request paper copies**; **close account** (external users). | 🟡 visibility only |

### 5.25 Audit log (`/audit`)
| ID | Requirement | Status |
|---|---|---|
| AUD-01 | Every insert/update/delete, sign-in, approval, export, file action: when, user, action, record, change (before → after), source (web/portal/device). Search, filter, export. | ✅ |
| AUD-02 | Append-only, kept 7 years (documented retention + no delete policy). | 🟡 append-only verify; retention not documented |

### 5.26 Data import & export (`/data`)
| ID | Requirement | Status |
|---|---|---|
| DATA-01 | Templates with sample rows for: consultants (incl. status, former fields), clients & vendors (incl. existing MSA, W-9, COI, inactive), projects, placements & rates (AR/AP only), SOWs (with prior invoiced/paid), MSAs, timesheets, AR invoices, AP invoices (incl. old vendor payments), payments, expenses, expiring documents, users, W-2 payroll. | 🟡 code has 11 (companies, consultants, projects, agreements, sows, placements, ar_invoices, ap_invoices, tracked_documents, users, payroll); missing **timesheets, payments, expenses** |
| DATA-02 | Check file (dry run) with errors by line; import saves good rows; update existing by natural key (toggle); history (who, when, file, rows, result). | ✅ |
| DATA-03 | Export each entity in template columns; "export everything". | 🟡 export-everything verify |
| DATA-04 | Import side effects (spec §6.27): consultant status Active → activated, Former → former list; company row with Existing MSA ID → MSA created, W-9 = N → compliance item, COI date → COI item, Inactive → deactivated; SOW without MSA → placeholder MSA; "Try with sample data". | 🟡 verify each |

### 5.27 Smart suggestions / AI
| ID | Requirement | Status |
|---|---|---|
| AI-01 | Rule-based ranked suggestions from live data, role-scoped (overdue AR, exceptions, SOW near ceiling, flow-down amendment missing, bench consultant for ending placement, I-9 reverification, low W-2 margin < 18 %, missing timesheets; platform: stalled tenants, suspicious sign-ups; consultant: own to-dos). | 🟡 verify bench/margin/flow-down rules |
| AI-02 | Ask a question in plain English using only allowed data (Anthropic or DeepSeek). | ✅ |
| AI-03 | Drafted e-mails (AR-08). | ❌ |

### 5.28 Notifications & scheduled jobs
| ID | Requirement | Status |
|---|---|---|
| NOT-01 | Catalog of functional §4 (invitation, registration, workspace ready, timesheet, invoice, AR courtesy/overdue, contract ending, document expiring, policy, signature events). De-duplicated daily cron. | ✅ |
| NOT-02 | AP payee notified when invoice matched, held, scheduled, paid. | ❌ (e-signature side done 2026-10-17: every admin of the counterparty company is notified when an envelope is sent) |
| NOT-03 | Unsigned envelope: remind every 3 days, escalate after 9. | 🟡 escalation verify |
| NOT-04 | SMS channel for timesheet reminders. | ❌ (needs SMS provider) |

### 5.29 Security checklist & billing tests (lessons from the old project — checks, not features)
Source and reasoning: [legacy-contrack.md](legacy-contrack.md) §2–3. These add **no new screens**; they are verified in
Phase 0.4 and applied whenever the matching code is touched.

| ID | Check | Status |
|---|---|---|
| SEC-01 | One-time codes use `secrets` (CSPRNG). | ✅ |
| SEC-02 | Per-code attempt limit **and** app-level rate limits on `/v1/public/*` and every code send/verify endpoint. | 🟡 attempts only |
| SEC-03 | Code resend: 60 s cooldown, max 5/hour per recipient. | 🟡 |
| SEC-04 | 5 wrong tries burn the code; constant-time compare. | 🟡 |
| SEC-05 | Sign-up / sign-in / reset responses identical whether or not the account exists. | ❓ |
| SEC-06 | Every code has an expiry checked on use. | ✅ e-sign / ❓ rest |
| SEC-07 | **No self-approval:** approver ≠ requester (and second approver ≠ first) on every approval write. | ❓ |
| SEC-08 | Role/permission changes validated before any write; whole transaction fails on error. | ❓ |
| SEC-09 | Short-lived access tokens. | ✅ |
| SEC-10 | Strict Content-Security-Policy; consider cookie sessions. | 🟡 |
| SEC-11 | Production deploys only from a push to `main`; PR code never runs with secrets. | 🟡 |
| SEC-12 | Upload allow-list (types, size), server-side content sniffing, user files served as attachments, no inline SVG/HTML. | 🟡 |
| SEC-13 | Every query scoped by tenant (RLS) and by party; two-tenant test per router. | 🟡 company profile cross-tenant read fixed 2026-10-17 (migration `20261016001300`, regression test); two-tenant test per router still outstanding |
| SEC-14 | CSV formula-injection protection. | ✅ |
| SEC-15 | Lockfiles, `npm ci`, pinned Python versions. | 🟡 |
| SEC-16 | One-time secret scan of the repo and its history. | ❓ |
| SEC-17 | Every list endpoint paginated or limited. | 🟡 |
| SEC-18 | Per-user cap on AI "Ask" usage. | ❓ |
| BILL-01…14 | Billing acceptance tests (only approved time billed; no double billing; exact decimals; rate changes never rewrite history; adjustments not edits; part payments; reminders skip paid; audit of every money action; margin from approved time). Full list in legacy-contrack.md §3. | ❌ write as tests with AR/AP/TS items |

---

### 5.30 Approved workflow (owner e-mail 2026-10-15 — overrides the prototype where they differ)
Flow: Register → Verify → **NDA** → MSA → Project → **SOW (under the project)** → Acceptance → **Resource contract** →
Acceptance → Timesheet → Invoice → Payment → **Payment confirmation**. Internal release **2026-10-25**, internal go-live
**2026-10-30**. Business logic before UI. Plan: [superpowers/plans/2026-10-15-workflow-master-spec.md](superpowers/plans/2026-10-15-workflow-master-spec.md).

| ID | Requirement | Status |
|---|---|---|
| WF-01 | Tenant workflow switches `requireNDA`, `requireMSA`, `requireAcceptance`, `requireContract` (default on), editable by the company admin; every gate reads them — no hard-coded gates. | ✅ built 2026-10-15 on `feat/wf-workflow` — API tests written, **not yet run in CI** |
| WF-02 | NDA with each client/vendor company before its MSA (when `requireNDA`); NDA status and acceptance history stored and audited. | ✅ built 2026-10-15 on `feat/wf-workflow` — API tests written, **not yet run in CI** |
| WF-03 | Project can't be **activated** until the client's NDA and MSA requirements are met (per switches). | ✅ built 2026-10-15 on `feat/wf-workflow` — API tests written, **not yet run in CI** |
| WF-04 | **SOW belongs to a project**; a project has many SOWs; a SOW has one or many resources (placements), each with its own contract, acceptance, timesheets, invoices, payments, confirmation. `POST /projects/{id}/sows`, `GET/POST /sows/{id}/resources`. | ✅ built 2026-10-15 on `feat/wf-workflow` — API tests written, **not yet run in CI** |
| WF-05 | Resource contract (vendor/contractor work order, or offer letter for W-2) required before timesheets when `requireContract`; must be accepted (signed or manually accepted) when `requireAcceptance`. | ✅ built 2026-10-15 on `feat/wf-workflow` — API tests written, **not yet run in CI** |
| WF-06 | **Acceptance records** (entity, accepted by, when, method e-sign/manual) + history; e-sign completion writes one. | ✅ built 2026-10-15 on `feat/wf-workflow` — API tests written, **not yet run in CI** |
| WF-07 | Engagement types as a lookup table (code, name, active, behaviour) — C2C, **E2E (employer-to-employer)**, 1099, W-2 — new types without schema change. | ✅ built 2026-10-15 on `feat/wf-workflow` — API tests written, **not yet run in CI** |
| WF-08 | **Naming engine**: per-tenant templates stored in the database (`PROJ-{YEAR}-{SEQ}`, `MSA-{CLIENT}-{SEQ}`, `SOW-{PROJECT}-{SEQ}`, `INV-{YYYYMM}-{SEQ}`, `CON-{YEAR}-{SEQ}`), custom placeholders, new entity types by config. | ✅ built 2026-10-15 on `feat/wf-workflow` — API tests written, **not yet run in CI** |
| WF-09 | Payment status (pending → processing → completed → **confirmed**) and **payment confirmation** (who, when) that closes the financial lifecycle. | ✅ built 2026-10-15 on `feat/wf-workflow` — API tests written, **not yet run in CI** |
| WF-10 | Status / approval / acceptance / payment history for major entities (audit log + acceptance + payment confirmation). | 🟡 audit log + acceptance history + payment confirmation; no per-entity status-history screen |
| WF-11 | Workflow tests: single- and multi-resource SOW, NDA/MSA on/off, C2C/E2E/1099, invoice generation, payment lifecycle + confirmation, naming templates. | 🟡 written (not run in CI): single + multi resource, NDA/MSA/contract switches on/off, E2E onboarding, naming, payment lifecycle, full chain for C2C; 1099 / E2E full chain not yet |

### 5.31 Platform admin, company ownership, roles & permissions, MFA (owner request 2026-10-15)
No "workspace" in the product: **any user creates a company → the platform admin activates it → the creator is its
owner.** Internally one company = one tenant. Plan: [superpowers/plans/2026-10-15-platform-admin-ownership-rbac-mfa.md](superpowers/plans/2026-10-15-platform-admin-ownership-rbac-mfa.md).
Built 2026-10-15/16 on branch `feat/p-platform-owner` (local only, not pushed, prod DB untouched); 86 API tests pass
(incl. 14 new) + 12 unit; browser QA of every scenario against a local database.

| ID | Requirement | Status |
|---|---|---|
| P-01 | Any signed-in user creates a company (`POST /onboarding/accounts`, wizard under My companies); it waits for activation — only its profile is usable meanwhile; max 3 pending per person; drafts abandoned 7 days are purged daily. | ✅ |
| P-02 | Platform admin activation queue: review company + W-9 (file link) + checks → Activate / Ask for more info / Reject (note required, owner e-mailed). The company's own record can't be self-activated. | ✅ |
| P-03 | Platform admins add / remove platform admins (not themselves). | ✅ |
| P-04 | Exactly one **owner** per company (`tenants.owner_membership_id`); **Transfer ownership** (old owner stays admin); owner can't be demoted or deactivated; platform can reassign an owner who left. Company profile shows Owner / Co-owner. | ✅ |
| P-05 | Permission core: per module none / view / edit, checked once in `tenant_db` by URL prefix; owner always has full access. | ✅ |
| P-06 | Owner-only **Roles & permissions**: custom roles on a base role + per-person exceptions (e.g. F1 finance view-only, F2 finance full); menu hides hidden modules; list pages hide create buttons when view-only. | ✅ |
| P-07 | MFA is the **user's choice**: owner/admin offers or withholds the option per user; users turn it on/off in Account; nobody is forced (REQUIRE_MFA_FOR_MONEY_ROLES removed); once on, every session needs the code. | ✅ (real TOTP enrollment needs Supabase — checked locally by simulation) |
| P-08 | Platform dashboard: users (total/new/active), companies (total/active/waiting/new), onboarding pipeline, SaaS MRR/ARR/ARPU by plan, money moving (invoiced/collected/outstanding/AP), 12-month trend, per-company totals. | ✅ |
| P-09 | Say "company", not "workspace", everywhere users can see. | ✅ |
| P-10 | RULE-05 amended (see §1). | ✅ |
| P-11 | Old `/signup` request form and "Create workspace" removed (the wizard replaces them). | ✅ |
| P-12 | Permissions that **widen** a base role (e.g. account manager editing invoices) — needs ~120 API role checks + 69 RLS `can()` calls rewritten. | ❌ follow-up |

## 6. Open decisions (product owner)

| # | Decision | Options | Blocks |
|---|---|---|---|
| D1 | Pricing | Prototype: per seat $29 / $49 / $79, minimum 3 / 5 / 15 seats, external users free (older screen: flat $299 / $799 / custom). Code: $12 / $20 / $32 per active user. | PLAT-09 |
| D2 | Production e-mail | Resend (docs) vs Zoho SMTP (running) | Phase 0 |
| D3 | AI provider | Anthropic vs DeepSeek (running) | AI-02/03 |
| D4 | Trial length | Prototype 14 days, code 30 days | PLAT-07 |
| D5 | Verification providers | IRS TIN match, Secretary of State, OFAC, bank verification — which vendors, or manual checklist for now | REG-06 |
| D6 | Tenant onboarding steps | Prototype list (PLAT-05) vs current functional §3.2 list | PLAT-05 |
| D7 | SMS provider | Needed for SMS reminders and SMS sign-in at scale | NOT-04 |
| D8 | Payment runs | Generate NACHA file only, or integrate a bank/payments API | AP-05 |
| D9 | Production sender domain for e-mail (Zoho SMTP, smtp.zoho.in:587) | `verify@mytrakin.com` (old project; note the **k** spelling — the old Azure domain, now dead) vs `verify@esgos.app` (current local `.env`) vs a sender on the live web domain **`mytrackin.com`** (**ck** — see [auth-setup.md](auth-setup.md)); set SPF/DKIM/DMARC for the chosen one | Phase 0.2 |

D7 note: if SMS is wanted, the team has used **Twilio** before (see legacy-contrack.md §1.2).

---

## 7. Backlog — work order (do top to bottom)

Size: S ≤ 1 day · M 2–4 days · L 1–2 weeks. Each line is one PR.

### Phase 0 — confirm the base (before new features)
| # | Item | IDs | Size |
|---|---|---|---|
| 0.1 | Click through every ✅/🟡 item in §5 for each role with seed data; fix statuses in this file | all | M |
| 0.2 | Go-live checklist section A against the live `bom1` deployment | — | S |
| 0.3 | Fix doc drift: README/deployment say `iad1`, Resend-only, Anthropic-only | D2, D3 | S |
| 0.5 | Verify the security checklist (SEC-01…18) against the code; fix what fails; one secret scan of the repo | §5.29 | M |
| 0.4 | Get D1–D8 decided | §6 | — |

### Phase P — platform admin, ownership, roles & permissions, MFA (owner request 2026-10-15)
| # | Item | IDs | Size |
|---|---|---|---|
| P.1 | Company accounts + activation + ownership + roles + MFA + dashboard | P-01…P-11 | ✅ done, local branch `feat/p-platform-owner` |
| P.2 | Owner: review, push, apply migrations `20261016000100…0400` to prod (in order), deploy | P-01…P-11 | S |
| P.3 | Widening permissions beyond the base role | P-12 | L |

### Phase W — approved workflow (owner e-mail; internal release 2026-10-25) — do before Phase 1
| # | Item | IDs | Size |
|---|---|---|---|
| W.0 | Get CI green (3 failing company-onboarding tests) | — | S |
| W.1 | Workflow switches + gate helper | WF-01 | S |
| W.2 | Engagement types table incl. E2E | WF-07 | M |
| W.3 | Naming engine | WF-08 | M |
| W.4 | SOW → project link, project SOWs + resources endpoints | WF-04 | M |
| W.5 | NDA/MSA gates (MSA create, project activation, invoices, vendor payments, new SOWs) | WF-02, WF-03, AGR-09 | M |
| W.6 | Acceptance records + resource-contract gate on timesheets | WF-05, WF-06 | M |
| W.7 | Payment status + confirmation | WF-09 | M |
| W.8 | Money-safety fixes: no re-opening invoiced timesheets; reminder link | TS-07 | S |
| W.9 | End-to-end workflow tests (single/multi resource, switches on/off, C2C/E2E/1099) | WF-11 | M |
| W.10 | Minimal UI for W.1–W.7 (settings switches, project SOWs/resources, accept, confirm payment) | WF-* | M |

### Phase 1 — money & control gaps (highest business value)
| # | Item | IDs | Size |
|---|---|---|---|
| 1.1 | Payment ledger page | LED-01 | S |
| 1.2 | Credit notes | AR-06 | ✅ 2026-10-18 |
| 1.3 | My approvals inbox (existing approval types first: timesheets, expenses, time off, AP exceptions, registrations) | APR-01, APR-02 | M |
| 1.4 | Approval chains + thresholds + dual approval for payment runs | APR-03 | L |
| 1.5 | Bank-detail change with second approver + callback | APR-04 | M |
| 1.6 | Rate-change request/approval | APR-05 | S |
| 1.7 | Org chart + delegation | APR-06, APR-07 | M |
| 1.8 | Account-manager client scope (DB + RLS + API + UI) | ACC-03, USR-02 | M |
| 1.9 | Signing-limit enforcement for countersigners | ACC-05, ESG-07 | S |
| 1.10 | Remittance e-mail + NACHA file | AP-05, AP-06 | M |
| 1.11 | Payout hold on expired COI / missing W-9 (if 0.1 shows it's missing) | AP-09, PAY-02 | S |
| 1.12 | Timesheet adjustment after approval | TS-07 | ✅ 2026-10-18 |

### Phase 2 — visibility & everyday usability
| # | Item | IDs | Size |
|---|---|---|---|
| 2.1 | Global search | UX-02 | M |
| 2.2 | Notifications bell + nav badges | UX-03, UX-01 | S |
| 2.3 | Reports hub (links + period/customer filter) | RPT-01, RPT-02 | M |
| 2.4 | Onboarding pipeline board + personal invite | ONB-01–03 | M |
| 2.5 | AI drafted collection e-mail + header AI drawer | AR-08, AI-03, UX-04 | M |
| 2.6 | Offboarding checklist + retention dates | WA-04, WA-05 | S |
| 2.7 | E-sign templates (NDA, offer, ICA) + template version / legal approval | ESG-02, ESG-08 | M |
| 2.8 | AP payee status notifications | NOT-02 | S |
| 2.9 | Time off pre-filled on timesheets | TS-10 | 🟡 2026-10-18 (approver notice left) |
| 2.10 | Per-page template/import/export toolbar | UX-10 | S |
| 2.11 | Access-matrix tab | ACC-04 | S |
| 2.12 | Import templates for timesheets, payments, expenses | DATA-01 | S |

### Phase 3 — SaaS platform
| # | Item | IDs | Size |
|---|---|---|---|
| 3.1 | Plans & billing + subscription invoices (after D1) | PLAT-09 | M |
| 3.2 | Auto-suspend after 60 days unpaid (read-only) | PLAT-10 | S |
| 3.3 | Support access (request → tenant approve → time-boxed → logged) | PLAT-11, PLAT-12 | M |
| 3.4 | Platform dashboard charts + funnel + KPIs | PLAT-01–03 | M |
| 3.5 | Tenant modules on create; check-in e-mail; steps aligned (D6) | PLAT-05–07 | S |

### Phase 4 — account, security, network polish
| # | Item | IDs | Size |
|---|---|---|---|
| 4.1 | Passkeys | AUTH-02 | M |
| 4.2 | Sign-in history, sessions list, recovery codes | AUTH-10, USR-05 | M |
| 4.3 | Re-auth before payments/exports; admin IP restriction | AUTH-07, AUTH-08 | M |
| 4.4 | Preferences (language, date format, start page, theme, list/cards) | USR-07, UX-08 | S |
| 4.5 | Notification channels matrix, digest, quiet hours | USR-06 | M |
| 4.6 | Privacy: download my data, paper copies, close account | USR-08 | M |
| 4.7 | Network: comments, post/message attachments, endorsements, profile strength, suggestions | NET-02, NET-04, NET-06 | M |
| 4.8 | Registration: terms/NDA/code-of-conduct acceptance | REG-04 | S |
| 4.9 | File thumbnails + 30-day trash restore | UX-06 | S |

### Phase 5 — integrations (Enterprise, on customer demand)
| # | Item | IDs | Size |
|---|---|---|---|
| 5.1 | External verification (TIN, SoS, OFAC, bank) | REG-06 (D5) | L |
| 5.2 | SCIM provisioning + SSO settings tab | SET-04 | L |
| 5.3 | Accounting sync (QuickBooks) for ledger | LED-01 | L |
| 5.4 | Payroll-provider export/import (ADP, Gusto, Paychex) | PAY-04 | M |
| 5.5 | SMS reminders | NOT-04 (D7) | S |
| 5.6 | Scheduled monthly report pack | RPT-03 | S |

---

## 8. Working rules

- Run locally: [README.md](../README.md). Architecture & extending: [technical.md](technical.md).
- New tables: tenant-scoped, RLS policy, **new** migration in `supabase/migrations/` (never edit an applied one).
- Keep RULE-01…06. Amount masking is checked in review for every new screen and CSV.
- UX reference is the prototype: open it, switch "Demo role", compare screen by screen.
- One backlog item per PR; PR title starts with the requirement ID; update the status here in the same PR.

---

## 9. Progress log (newest first — every session adds one line)

Format: `YYYY-MM-DD · IDs touched · what changed · what is left / uncommitted`.

- 2026-10-21 · timesheet client approval rollout · **B's approval now actually flows to A**: A's approval used
  to require a representative inside B's workspace (nobody had one), so weeks finalised at B silently. Now the
  placed-by approval e-mails the client's own-workspace people (or its invited representative) a personal,
  expiring approval **link** (hashed token, `ts_approval_view` / `ts_client_decide` SECURITY DEFINER) — public
  page `/approve/timesheet/{token}` — Approve finalises + auto-invoices, Return-with-note rejects back to the
  consultant and alerts both sides. B-only shortcut only when A has no workspace people and no rep.
  `20261021000400` applied to production; e2e tests added (approve→auto-invoice, return-with-note).
- 2026-10-21 · AR-01 · **Auto-invoicing on final timesheet approval**: placed-by manager approves → end-client
  representative e-mailed and approves → `generate_invoices` runs automatically on a system connection
  (AR bill-rate × approved hours, AP pay-rate × hours, dedupe + MSA guards), drafts ready for finance.
  Verified the generation pipeline in a rolled-back transaction (correctly skipped an already-invoiced week).
- 2026-10-21 · RLS regression fix · **Timesheets 500 for every role**: the 20261021000200 client policies
  queried `timesheet_entries` inside a policy chain that `entries_read` loops back into `timesheets` →
  Postgres "infinite recursion detected in policy" at plan time → every timesheet query 500'd on production.
  Fixed with `SECURITY DEFINER` helper `client_is_end_client(consultant)` on placements
  (`20261021000300`), applied to production directly (fix is DB-only, no deploy). Reproduced in-process,
  verified all roles plan cleanly; regression test added (`test_timesheet_policies_do_not_recurse`).
- 2026-10-21 · timesheet approval chain (QA) · **Placing company could not approve (403 "not part of the
  placement chain")**: "Placed By" was matched via `tenants.company_id`, null for most workspaces; now it is
  the workspace that owns the timesheet. End-client approval engages when that company has a representative
  member in the placing workspace (`client_user`, company_id set) — RLS `20261021000200` lets them read and
  approve, UI shows "Approve (end client)", e-mail tells them it is their turn; no represented end client →
  placed-by approval finalises so invoicing unblocked. All four live submitted weeks resolve correctly.
- 2026-10-21 · TS-08 weekend confirmation, timesheet two-level approval · **Weekend hours now need the
  consultant's confirmation before approval**: approver asks (optional note) → e-mail + banner to the
  consultant → consultant confirms → approver e-mailed, gate lifted; reject/resubmit resets the state; reject
  also e-mails the reason. Fixed two-level approval ("Placed By" = the placing workspace, not the AP payee;
  no external end client → one approval finalises) and applied the forgotten `20261020000100` and new
  `20261021000100` migrations to production (the missing apply was the timesheet 500).
- 2026-10-19 · Strike T011303-1037/1045/1046/1047/1048/1049 · **Six QA tickets.** 1049: the 1049: the New-project client list
  only held our own workspace's companies, so the MSA counterparty could not be picked (tester picked their own
  company → "no active MSA"); now `/projects/counterparties` offers every company with an MSA in force either way, and
  `workflow.has_active_agreement` also counts an MSA the other company sent us (`shared_agreements`). 1047: projects
  another company assigned to us by a sent SOW are offered in New placement (`shared_projects()`); placing someone
  creates our own copy (`projects.source_project_id`, prime = that company, AR defaults to it). 1048: MSA payment
  terms / renewal / notice / insurance are dropdowns. 1037: a company still being set up shows no admin menu or
  "tenant admin" role. 1045/1046: mail left our server at once (notifications all `sent`); delay/loss is downstream —
  added Date, Message-ID and a real text part; **owner: add a DMARC record for esgos.app**. Migration
  `20261019000100_shared_projects.sql` must be applied to prod before deploy (`/projects/shared` needs it).
  Cross-company names on projects/placements now fall back to `company_public_name`. Browser-QA'd on local QA DB.
- 2026-10-19 · TS-01…09, AR-01 · **Timesheets browser-tested end to end** (local QA DB; consultant, finance, vendor):
  enter / save / reload / submit / lock, checks flag a 17-h day, return with reason, consultant fixes + resubmits,
  approve, approve-all-that-pass, history + CSV, vendor read-only without money, consultant kept off the staff list,
  invoices from the approved week (24 h × $95, 16 h × $105) — 31/34 pass. Gaps found: TS-04 KPIs and "Remind not
  submitted" missing (status corrected to 🟡); unsent draft AR invoices show "Open" in the AR list (live_status
  ignores draft, so drafts also count in balances/aging); week list Checks column off-screen at 1280 px.

- 2026-10-18 · AR-06, TS-07, TS-10 · **Credit notes, adjustment after invoicing, time off on the timesheet.** New
  `credit_notes` table (migration `20261018000100`, RLS: staff + the billed customer read, finance writes; audited);
  `invoice_balances.balance` now subtracts credits (new `credited` column), so aging, payment caps and pay-when-paid
  release follow. `POST /invoices/{id}/credit-notes` (sent AR only, ≤ open balance minus in-flight payments,
  number `CN-{YEAR}-{SEQ:4}` from the numbering engine), `GET /credit-notes` (status open → applied once the invoice
  is settled); invoices with credits can't be voided. Web: Credit notes tab, credits + "Issue credit note" on the
  invoice. TS-07: re-opening an invoiced week names the invoice and says void / credit note / extra invoice;
  "Request adjustment" wording on approved weeks. TS-10: approved time off shown as a read-only row on My timesheet.
  Left: credit-note void, customer credit carried to another invoice, client-approver notice for time off (no
  approver e-mail on projects), prod migration. main CI was already red (~14 team tests) before this change.
- 2026-10-17 · AUTH · **Sign-in codes were unenterable.** "E-mail me a code" sends Supabase's default **8-digit**
  OTP, but `CodeEntry` in the login page required exactly 6: `pattern="\d{6}"`, `maxLength={6}` and a button
  disabled until `code.length === 6`. The last two digits could not be typed, native validation rejected the form
  and the button stayed grey — nobody could sign in with a code at all. The field now takes 6–8 digits and
  enables at six or more, which covers e-mail (8), SMS (6) and any future change to the project's OTP length; the
  label and the "we sent a … code" messages no longer assert a length. The TOTP field stays at 6 digits, which is
  correct for an authenticator app. Verified tsc + next build; there is no automated coverage of this screen.

- 2026-10-17 · AGR-04, AGR-05 · **A signature is never refused.** Signing the Velocity ↔ DREP MSA failed with
  "There is already an active MSA between these two companies (MSA-DREPSOFTWARE-001)". Velocity had raised a
  counter-MSA while DREP's was `out_for_signature` — the trigger counts only pending/accepted/active as live, so
  an unsigned copy did not block a second one — leaving two MSAs waiting on each other. When the last signer
  finished, sealing the envelope set the agreement to `accepted`, the same trigger fired on that UPDATE, found the
  other pending MSA and raised, **rolling the whole transaction back**: the signature was real and already in the
  audit trail, yet the signer was shown a conflict. The rule now guards *creating* a second live MSA (where
  duplicates come from) and never blocks a status change on an agreement that already exists; when an MSA comes
  into force the opposite-direction copy that has not is superseded with a note naming its replacement, while one
  already in force is never quietly ended by another party's signature. Migration `20261016001800`, applied.
  Regression test in `tests/test_msa_lifecycle.py`; verified live on a throwaway pair that the signature now
  completes, the unsigned copy is superseded, a genuine duplicate is still refused at creation, and a pre-existing
  pair of in-force MSAs still signs cleanly. **Seen but not fixed:** agreement codes and envelope numbers are
  unique per workspace only, so two different workspaces both hold `MSA-VELOCITYWORK-001` and two both hold
  `ENV-00002` — which is what made this ambiguous to diagnose.

- 2026-10-17 · AGR-05 · **SOWs run both ways under one MSA, with approval.** An MSA between two companies is one
  agreement whichever workspace recorded it, so work under it has to be possible from either side. It was not:
  `POST /sows` read the agreement with a plain SELECT and the restrictive tenant-isolation policy hides another
  workspace's rows, so the company an MSA was *sent to* got a 404 for an MSA it could see in `GET /agreements`;
  and a SOW copied `company_id` off the agreement, which from the counterparty's side is its *own* company, so a
  reverse SOW would have pointed back at the sender. Now the agreement is resolved from either side and
  `mytrakin.agreement_peer_company()` names the other party from wherever you stand. On top of that, SOWs get the
  same approval shape as MSAs: `draft` (invisible to the other company) → sent → approved (`active`) or turned
  down with a reason; `POST /sows/{id}/submit` and `POST /sows/{id}/respond`, migration `20261016001700`. A sent
  SOW is shared read-only **without money** — reference, title, term, status — while value, invoiced, paid, burn
  and amendments stay in the workspace that created them, so the AR/AP amounts that RULE-01 protects never cross a
  workspace boundary. Verified end to end against the live ESG ↔ Velocity MSA: reverse SOW created, invisible
  while a draft, visible once sent, the creator refused (MT403), rejection without a reason refused (MT422),
  approval → active, rejection reason kept, third workspace sees nothing. Tests in `tests/test_sow_two_way.py`;
  ruff, tsc and build green. **Left:** the DB-backed pytest suite still needs a machine with Postgres.

- 2026-10-17 · CON-02, U-ID · **Anybody on the platform is findable; U-IDs are on profiles.** The consultant picker
  only listed people already linked to your workspace, so a colleague with an account who had never worked with you
  came back as "Nobody matches"; `GET /consultants/candidates` now searches every registered user by name, U-ID or
  e-mail (id, U-ID, name, e-mail and mobile only, and a two-character term is required, so it is not a user
  directory to browse). Onboarding somebody new to the workspace was also broken for HR, account managers and legal:
  it inserts a membership and `memberships` is tenant-admin-only under RLS, so only an owner could do it by hand —
  `mytrakin.grant_consultant_access()` (migration `20261016001600`) is now the way in, and may only create a
  consultant membership or attach the consultant link to an existing member. And the U-ID was missing from profiles
  entirely: `/network/me` and `/network/people/{id}` return `user_code` and both profile views show it.
  **Consequence:** a consultant must have a myTrakIn account somewhere (owner's decision) — there is still no manual
  entry for somebody who has never signed up. Tests in `tests/test_consultant_picker.py`; ruff and tsc green;
  the DB-backed suite still needs a machine with Postgres.

- 2026-10-17 · CON-02 · **A consultant is picked, not typed.** "Onboard a consultant" no longer asks for a name in a
  free-text box: `GET /consultants/candidates` lists the people registered with this workspace (members plus people
  added to its companies), each with their U-ID, searchable by name, U-ID or e-mail. Picking one fills the e-mail and
  mobile, and `POST /consultants` now takes `user_id` and reads name/e-mail/mobile **from the profile server-side** —
  the form no longer supplies them, so a consultant cannot be created as a near-duplicate of somebody already here.
  The same person cannot be onboarded twice (409, rehire covers that). Fixed a related bug this exposed: because
  `memberships` is unique on (tenant, user), onboarding someone who already had a role here would have silently
  kept that role and never given them consultant access; the membership now keeps its role and gains the consultant
  link. A user from another workspace is refused, and the old name+e-mail payload no longer validates.
  **Consequence:** a consultant must already have a myTrakIn account (owner's decision) — there is no manual entry
  for somebody who has never signed up. Tests in `tests/test_consultant_picker.py`; 115 API tests pass; ruff, tsc and
  next build green.

- 2026-10-17 · ESG-02, NOT-02 · **Send for signature reworked.** Signers are no longer typed in: you are fixed as
  signer 1 (your company) and the rest are picked from the other company's own admins/owners, strongest role
  first, with an e-mail invite box only when that company has no admin with an account (`GET /envelopes/signing-parties`,
  `company_signing_admins()` — name, e-mail and role only, cross-workspace, nothing else of that company).
  An envelope now carries several PDFs (`envelope_documents`, merged in order, add/remove while it is a draft);
  sending e-mails **every** admin of the counterparty company, recorded as `counterparty_notified`. The form field
  is labelled "Note". Migration `20261016001400`. Tests in `tests/test_esign.py`; 109 API tests pass, ruff/tsc/build
  green. **Left:** ESG templates (NDA / offer / ICA) and template versioning are still missing — the other half of
  ESG-02 and all of ESG-08.

- 2026-10-17 · RULE-01, SEC-13, CO-03, AGR-07 · **Security fix + CI green.** The cross-tenant directory had left the
  `companies_directory` policy from migration 0780 in place: "any signed-in member may select any company" with no
  tenant filter, so any user could read every workspace's contact e-mail, address, EIN, W-9 data and notes
  (`GET /companies/{id}` answered 200 for another workspace). Migration `20261016001300` drops it — the picker and
  counterparty names already go through the narrow helpers of migration 1000 — and a company outside your workspace is
  now 404. Same fix makes `POST /companies/{id}/msas` from an unreadable company 404 instead of 403. Also: the
  agreement **list** now resolves a cross-tenant counterparty through `company_public_name()` (it showed blank while
  the detail endpoint didn't), and `test_non_staff_can_upload_session_w9` got its own EIN (it reused the shared
  fixture EIN another test in the workspace had registered). Regression test in
  `test_directory_spans_tenants`. All 104 API tests pass; ruff, tsc and `next build` green. **Left:** SEC-13 is only
  partly done — a two-tenant test per router is still outstanding (Phase 0.5). Uncommitted.

- 2026-10-16 · AGR-07 · MSA lifecycle: pending → accepted | rejected (with note) → expired; one live MSA per pair
  (trigger, both directions); renewals requested by either company, accepted or declined with a note. Migrations
  `20261016001300` + `001301`. Gates count accepted/active only. Verified live with two temp workspaces (19/19).
  Written test `tests/test_msa_lifecycle.py` runs in CI. Open: the counterparty's answer is in-app only (no e-mail yet).
- 2026-10-16 · AGR-07 · Agreements shared with the counterparty: an agreement recorded by one workspace is visible,
  read-only and from the counterparty's side, in the workspace of the company it is with, with its files
  (`shared_agreements()`, `shared_agreement_files()`, migration `20261016001200`). Verified live with a temp workspace
  for Lensify (DREP's MSA visible, detail + file list, upload refused). Written test
  `test_counterparty_sees_the_agreement_and_its_files_read_only` runs in CI. Open: the counterparty can't yet accept or
  sign a requested MSA from its side; that's the next step.
- 2026-10-16 · CO-03, AGR-07 · Business IDs unique platform-wide (`C-` + sequence, migration `20261016001100`;
  duplicates renumbered); agreement with the company itself refused by the API and excluded from the picker.
  Verified live. Committed to main.
- 2026-10-16 · CO-03, AGR-07 · Company directory spans tenants: picker lists every active company;
  cross-tenant MSA counterparty works end to end (directory + propose + name display). Directory columns only;
  money/profiles stay tenant-scoped. Migration `20261016001000`, verified live. Committed to main.
- 2026-10-16 · CO-03, AGR-07 · Agreement entry UX: Agreement ID always auto-numbered (field removed);
  CompanyPicker is a type-ahead with suggestions + real loading/error states; consultant picker shows name + U-ID.
  Committed to main.
- 2026-10-16 · CO-01, CO-02 · "What does your company do" is multi-select: companies.kinds holds every role,
  kind stays primary; creation doesn't ask — new companies start with all four roles, narrowed on the profile
  if needed. Wizard, staff form, list/detail/directory/filters show and filter all roles. Migration
  `20261016000900`, verified live (create/filter/patch/invalid-rejected). Committed to main.
- 2026-10-16 · P-01 · Draft companies are visible and discardable: closing the wizard early left an invisible
  tenant counting toward the 3-pending cap. My companies now lists drafts (Resume inside the same account, Discard
  via `DELETE /onboarding/accounts/{id}`); submitted companies can't be discarded. Migration `20261016000800`,
  verified live (draft → visible → 429 at cap → discard → cap freed). Committed to main.
- 2026-10-16 · W-9 extraction (company onboarding) · March-2024 W-9 with a wrapped section-1 label no longer
  bleeds the wrap into `legal_name` (DREP case); pure-function regression test `tests/test_w9_parse.py`. Committed to main.
- 2026-10-16 · TS, AR, AP, WF-09, U-ID, ESIGN · Live click-test of every role + full money flow (timesheet → return →
  resubmit → approve → invoice → pay-when-paid → payment run → vendor confirm; e-sign 2 signers). 6 bugs fixed with
  regression tests (migrations 20261016 0500–0700, cron, web dates, e-sign recipients); 94 API tests pass. Open: draft AR
  invoices still show "Open" and count in the dashboard's AR total (product decision). Committed to main.
- 2026-10-16 · CO-03, AGR-07 · Company-initiated MSAs on main: searchable company directory + `POST /companies/{id}/msas`
  (record signed / request new, NDA gate, numbering, counterparty e-mail) with a `CompanyPicker` on the company profile
  and contracts modal. Fixed vendor 403: migration `0800` lets membership-linked vendor/client admins pass the
  agreements INSERT policy (verified live 201 as vendor_admin, visible on company page). Left: CI run of the API suite
  (no local Postgres), click-test per role.
- 2026-10-16 · P-01…P-12, RULE-05 · Phase P built on local branch `feat/p-platform-owner` (from main ca8aa71): company =
  account with platform activation, owner + transfer, owner-only roles & permissions, MFA as the user's choice,
  platform dashboard, "workspace" wording removed. 86 API tests pass (3 pre-existing failures: 2 team W-9 tests +
  smart suggestions without an AI key) + 12 unit; browser QA (6 scenarios) on a local DB. Not pushed; prod DB untouched.
- 2026-10-15 · WF-01…11, RULE-07, AGR/PRJ/TS gaps · Owner e-mail "master specification" adopted (wins over prototype;
  E2E = employer-to-employer; business rules first for 25 Oct). Added §5.30 + Phase W. Plans written (uncommitted):
  `superpowers/plans/2026-10-15-workflow-master-spec.md` (Phase W) and `…-contracts-projects-timesheets-gaps.md`
  (UI/prototype gaps, after go-live). Same day: Phase W W.0–W.10 implemented on branch `feat/wf-workflow` (11 commits,
  not pushed; ruff, tsc, `next build` and unit tests pass locally; API tests need CI). Left: push + CI, click-test per role.

- 2026-10-14 · AUTH-13 · Owner tested Google sign-in on https://www.mytrackin.com: it worked but showed the "Almost
  there / request a workspace" wall. Fixed on branch `feat/AUTH-no-workspace-home` (uncommitted→committed locally, NOT
  pushed): `member_db` dependency (`apps/api/app/deps.py`), network routes use it, `AppShell` limited menu + redirect,
  home → `/network`, welcome note + MFA tip on the feed. No migration needed (RLS already per-person). `tsc` passes; the
  new API test (`test_new_user_without_a_workspace_can_use_the_network`) has not run locally (no Postgres) — CI runs it.
  MFA is set up at avatar menu → Account & security → "Set up an authenticator app".
- 2026-10-13 · AUTH-01, AUTH-11, AUTH-12 · Login work on branch `feat/AUTH-login-mfa-social` (uncommitted): shared
  `components/auth.tsx` + `lib/authProviders.ts`, forgot-password + `/reset-password`, Google/Microsoft buttons on login
  and create-account, error mapping, MFA cancel link. `tsc` and `next build` pass; pages render (HTML checked on the
  running dev server) — **not click-tested with real providers**. Created Entra app "myTrakIn Sign-in" (client id
  `32328f1e-a9a5-43cf-943f-b40f26e82527`, secret in `ESG\_secrets\microsoft-signin.json`, expires 2028-10-13). **Waiting
  on owner** (details in [auth-setup.md](auth-setup.md)): Google OAuth client; enable Azure + Google in Supabase; URL
  Configuration; current publishable key (the key in `apps/web/.env.local` is rejected as invalid).
- 2026-10-13 · Azure shutdown · Owner asked to stop Azure billing for the old project; deleted resource group
  `rg-contrack` (details in [legacy-contrack.md](legacy-contrack.md)); verified the subscription is empty. **Open
  follow-ups for the owner:** (1) DNS for `mytrakin.com` still points at Azure — `www` is a CNAME to
  `contrack-esg-r620lc.azurewebsites.net` (now deleted: a dangling name someone else could claim) and the apex A record
  is an Azure IP. Remove/replace those records at the DNS provider, **keep the Zoho MX/SPF/DKIM records** (mail uses
  them), and remove any `asuid` TXT record. (2) The old repo's `deploy-production.yml` / `deploy-dev.yml` will fail on
  the next push — disable them. (3) Old `mytrakinprod` served ~290 requests/day (health checks/bots) and the dev app
  2–15k/day on `mytrakin.com` until deleted. Not done by me: nothing in the new project depends on Azure.
- 2026-10-13 · RULE-07, SEC-*, BILL-*, D9 · Reviewed the old Contrack project. Kept only: Zoho SMTP settings (already
  in the new API), SMS-provider hint (Twilio), a security checklist and billing acceptance tests. **No old
  functionality adopted** (owner's instruction) — see [legacy-contrack.md](legacy-contrack.md). Old `Backend\.env` has a
  plaintext DB password in a comment and the old audit mentions a Firebase key in git history: tell the owner to rotate
  if that project is live. Uncommitted.
- 2026-10-13 · — · Read the whole prototype; wrote this plan, [prototype-spec.md](prototype-spec.md), copied the
  prototype to `docs/prototype/`, added root `CLAUDE.md`. No code changed. Next: Phase 0.1 (verify statuses), then
  backlog 1.1 (LED-01). All four doc changes uncommitted.
