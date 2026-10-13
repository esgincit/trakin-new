# myTrakIn — functional specification

Version 1.0 · October 2026 · Audience: product owners, implementation consultants, customer administrators.

## 1. Purpose

US IT staffing companies rarely sit at one end of a deal. A typical chain is:

```
End client  →  Prime vendor  →  Your company  →  C2C vendor  →  Consultant
(Meridian)      (Northwind)      (ESG)             (BrightPath)     (Ravi)
```

Money moves link by link and each link is a separate contract. myTrakIn answers, at any moment:

- **Who owes us, how much, since when?** (AR — your customer's invoices)
- **Whom do we owe, and can we pay yet?** (AP — your vendor's or contractor's invoices, including pay-when-paid)
- **Where is each consultant's money stuck?** (payment flow across both links)
- **Are the contracts, hours and documents behind those payments in order?** (MSA/SOW, timesheets, I-9, insurance)

**Design rule — AR/AP only.** You see and store the two links you are party to. Other links (for example what the end
client pays the prime) are shown by name with a masked amount and are never recorded.

## 2. Users and roles

| Role | Typical person | Can |
|---|---|---|
| Platform owner | The company running myTrakIn as SaaS | See every workspace, approve sign-ups, create workspaces, change plans, suspend/close; see usage and revenue per user |
| Admin | Owner / COO of the staffing company | Everything in their workspace, users and roles, settings, reminder rules |
| Finance | Controller, AP/AR specialist | Invoices, payments, payment runs, rates, payroll, 1099, referrals, audit log |
| Account manager | Sales / delivery | Clients, projects, placements (bill rates), AR follow-up, contracts |
| Legal | Contracts manager | Agreements, SOWs, amendments, e-signatures, compliance, audit log |
| HR | Onboarding / HR generalist | Consultants, onboarding checklists, I-9 / work authorization, documents, policies, referrals |
| Approver | Delivery manager | Approve or return timesheets; expenses; time off |
| Viewer | Leadership, auditors | Read-only, no rates or AP amounts |
| Vendor | C2C vendor's account manager | Their consultants, their consultants' timesheets, their AP invoices and pay rates; submit invoices |
| Client | Customer contact | Invoices addressed to them and their projects |
| Consultant | W-2, C2C or 1099 worker | Their projects, timesheet, payment *status* (no amounts), SOW dates, work authorization, policies, agreements, expenses, time off |

Admins and Finance must use two-step verification before any money screen opens.

## 3. Modules

### 3.1 SaaS platform (owner console)

- **Sign-up**: a staffing company fills in company, contact, EIN, state, plan, seats. Automatic checks flag personal
  e-mail domains and a missing EIN; the submitter's IP is recorded.
- **Approval**: approve (creates the workspace, the first admin invitation and default reminder rules; 30-day trial),
  ask for more information, or reject — each sends an e-mail.
- **Dashboard**: workspaces by status, active users, MRR/ARR, revenue per user, new in 30 days, sign-ups waiting,
  workspaces inactive for 14+ days, per-workspace setup progress (1–8), users, consultants, placements, last activity.
- **Pricing**: per active user per month by plan (Starter $12, Growth $20, Enterprise $32 — configurable in
  `routers/platform.py`). Trials and non-active workspaces are not billed in MRR.

### 3.2 Workspace setup

Eight-step checklist shown in Workspace settings: company details → invite team → add clients & vendors → import
existing data → MSAs & SOWs → projects & placements → policies & reminders → go live. Step 8 sets the workspace live.

Settings: legal name, EIN, state; allowed sign-in methods (e-mail code, SMS code, SSO with domain, Google, Microsoft,
password); MFA for all staff; idle sign-out; invoice footer.

### 3.3 Onboarding companies (clients and vendors)

- Add manually, import from CSV (active and inactive, with MSA references), or approve a **public registration**.
- Public registration page per workspace (`/register/<workspace id>`): kind (client, vendor, 1099, consultant), legal
  name, contact, e-mail, phone, state, EIN, documents (W-9, incorporation certificate, insurance). Checks: personal
  e-mail domain, EIN present, possible duplicates (same name, EIN or e-mail).
- Approval creates the company (stage 2 of 8) or the consultant (onboarding) and moves the uploaded files to it.
- Company onboarding stages: Registered → Verified → Documents → MSA signed → SOW signed → Project set up → Timesheets → Invoicing.
- **Inactive** keeps all history; requires a reason; can be reactivated.

### 3.4 Consultants and onboarding

Engagement types and their checklists:

| Type | Checklist |
|---|---|
| W-2 full-time | Offer letter signed · Form I-9 Section 1 (by day 1) · Section 2 (within 3 business days) · E-Verify case · W-4 and state withholding · Direct deposit · Benefits enrollment · NDA · Policies · Background check · Projects & timesheet access |
| W-2 contract | Contract offer · I-9 §1 · I-9 §2 · E-Verify · W-4 · Direct deposit · NDA · Policies · Background check · Projects |
| C2C | Vendor has an active MSA · Vendor SOW/work order · Employer confirms work authorization · Vendor insurance covers consultant · NDA · Policies · Background check · Projects |
| 1099 | Independent contractor agreement · W-9 received and TIN matched · Classification review (1099 vs W-2) documented · Certificate of insurance (if required) · NDA · Policies · Projects |

Rules:
- Starting onboarding also invites the person to sign in as a consultant.
- **Finish onboarding** requires every item done (the "Projects assigned" item may still be open); it activates the
  consultant and their placements, which opens timesheets.
- **Offboard**: last day, reason, rehire eligibility. Ends all placements, deactivates the login, keeps everything.
- **Rehire**: only if eligible; restarts the checklist for the same engagement type.
- Former employees and resigned C2C/1099 contractors can be imported in bulk with end date, reason and rehire flag.

### 3.5 Contracts: MSAs, SOWs, amendments

- Agreement kinds: MSA (client or prime), subcontractor agreement (vendor), independent contractor agreement (1099),
  NDA, offer letter. You are the supplier, buyer or employer.
- Existing signed contracts are **recorded** (source "manual" or "imported") and the signed PDF attached; new ones are
  created as drafts and sent for e-signature.
- SOWs / work orders sit under an agreement: side *we bill* (client) or *we pay* (vendor / 1099), dates, value ceiling,
  amounts invoiced/collected before myTrakIn (for imports). A vendor SOW can be linked to the client SOW it supports and
  cannot end after it.
- **Burn**: invoiced ÷ ceiling; alerts at 90 %. SOWs ending in 60 days and MSAs in 90 days are counted on the dashboard
  and e-mailed to legal at 90/60/30 days.
- **Amendments** (extend dates, change value) are drafted, sent for signature, and applied automatically when signed.
- **Missing & expiring**: companies without an active MSA, consultants without their NDA / offer / contractor agreement,
  policies not accepted, documents missing or expiring within 120 days.

### 3.6 E-signatures

- Upload a PDF, add signers in order (or parallel), message, reminder interval (default 3 days); link valid 30 days.
- Signer steps: open link → confirm e-mail with 6-digit code → accept ESIGN/UETA disclosure → read the document →
  type or draw signature → confirm intent → sign. Or decline with a reason (sender is told).
- Evidence for every step: time (UTC), IP address, device, approximate city/region/country.
- Completion: sealed PDF = original + certificate of completion (signers, times, IPs, devices, document SHA-256,
  disclosure). Stored with its own SHA-256; everyone gets a 7-day download link. Agreements and SOWs become active;
  amendments are applied.
- Senders can remind, void (with reason) and download at any time.

### 3.7 Projects and placements

- Project: code, name, client, prime vendor (if you are a sub), dates, client timesheet approver, description, files.
- Placement = one consultant on one project with: role, dates, hours/week, end client (name only), **AR** customer + SOW +
  bill rate + terms, and **AP** payee (vendor company or the 1099 contractor) + SOW + pay rate + terms + pay-when-paid.
- W-2 employees have no AP payee (payroll). A consultant may have any number of placements at once.
- Rate changes are allowed for finance only and are audited; they apply to time not yet invoiced.

### 3.8 Timesheets

- One timesheet per consultant per week (Sunday–Saturday) covering all their projects, plus optional internal time.
- Consultant enters hours (0–24 per day, quarter hours), saves drafts, submits. Submitted/approved weeks are locked.
- **Automatic checks** shown to approvers: submitted · no day over 12 h · within weekly allocation · weekend hours ·
  overtime over 40 h for W-2 (1.5× pay) · every day inside the placement dates · enough value left on the SOW.
- Approvers approve, return with a reason (the consultant sees it), or **approve all that pass** for the week.
- Finance sees what approval will create: the AR amount and the AP amount for the week.
- Reminders: Friday (this week), Monday (last week), Tuesday (last week, HR copied).
- Vendors see their consultants' timesheets (read-only).

### 3.9 Invoices (AR and AP)

**AR (you bill your customer)**
- *Create invoices from timesheets* for a period: one draft per placement with approved hours not yet invoiced;
  amount = hours × bill rate; due date from terms; the matching AP payable is prepared at the same time.
- Manual invoice for a placement; send (e-mails the customer contact); void with reason (only without payments).
- Payments: amount, date, method (ACH, wire, check, card, other), reference. Part payments supported.
- Collections: notes per invoice; reminders 7 days before due (courtesy) and 1, 7, 15, 30 days after (day 30 copies finance).

**AP (your vendor / 1099 contractor bills you)**
- Vendors submit invoices in their portal: number, placement, period, hours. Amount = hours × pay rate.
- **Three-way match**: invoiced hours vs approved timesheet hours vs SOW rate. Mismatch → status *exception*; finance can
  accept at approved hours (amount recalculated) or ask the vendor to re-issue.
- **Pay-when-paid**: the AP invoice waits (*held*) for the matching AR invoice; when the customer pays in full it becomes
  *ready to pay* automatically.
- **Payment runs**: choose payable invoices, method and date; held and mismatched invoices are skipped.

**Statuses** — open · part paid · overdue · overdue part paid · paid · scheduled · held · ready to pay · exception · void.

### 3.10 Payment flow

One row per consultant and billing period showing every hop: end client → customer (masked, not tracked), customer →
you (AR invoice, amount, status, due date), you → payee (AP invoice or payroll), and the gap (AR − AP) when both are
visible to you. Filter open/all; search.

### 3.11 Payroll, 1099 and referrals

- **W-2 payroll results** (from ADP, Gusto, Paychex…): pay date, period, hours, gross, employer taxes, benefits, net.
  Entered or imported. W-2 margin report: billed vs fully loaded payroll cost per employee for a period.
- **Referral fees**: referrer (individual 1099, company, or employee), referred consultant, hourly fee per approved hour
  (optional cap) or one-time fee after an eligibility date. Earned, paid and due are calculated; individuals need a W-9
  before the first payment.
- **1099 summary** per calendar year (cash basis): AP payments to 1099 contractors and payments to individual
  referrers, W-9 status, and whether the total reaches the 1099-NEC threshold ($600 through 2025, $2,000 from tax year
  2026 — confirm yearly; the threshold can be overridden).
- **Expenses**: consultants submit (date, amount, category, project, billable); approvers approve/reject; finance marks
  reimbursed. **Time off**: PTO, sick, unpaid; approve or decline.

### 3.12 Compliance

- **Work authorization & I-9**: type, valid-until, I-9 status, E-Verify status, findings (expired → stop work and
  reverify; due within 90 days; not recorded). C2C: employer is responsible; 1099: no I-9.
- **Expiring documents**: I-9 reverification, passport, EAD, I-94, visa notice, COI, W-9, background check,
  certification, driver's license, agreement, other. Status, what it blocks (e.g. payouts), extra recipients.
  E-mails at 120/90/60/30/14/7 days before, on the day, then weekly until renewed. Renewal records the new date
  (and updates the consultant's work-authorization date for EAD / I-9).
- **Policies**: publish a version (PDF) for chosen engagement types; publishing retires the previous version. Consultants
  accept in their portal; acceptance stores time, IP address and device. Reminders on day 0, 7 and 14.
- **Reminder rules** (admin): turn each rule on/off and change its day offsets.
- **E-mail log**: every message, recipient, subject, status.

### 3.13 Import and export

Templates (CSV with sample rows): clients & vendors (active and inactive), consultants (current, onboarding, former),
projects, agreements, SOWs (with prior invoiced/paid), placements & rates, client invoices (history), vendor & 1099
invoices (including old vendor payments), expiring documents, users, W-2 payroll.

- *Check file* validates without saving (required columns, dates, numbers, e-mails, choices) and lists errors by line.
- *Import* saves row by row; a bad row never blocks good ones; re-importing updates by natural key (name, e-mail, code).
- Import history: who, when, file, rows created/updated/failed.
- Exports use the template columns (edit and re-import); plus payments, timesheets and audit log. Every list also has
  an *Export* button for exactly what is on screen (after search and filters).

### 3.14 Network

LinkedIn-style profile owned by the person and shared across workspaces: photo, cover, headline, location, about,
experience, education, certifications, skills, website, open-to-work. Visibility: everyone on myTrakIn, my companies
and connections, or my companies only; contact details shown to connections if allowed. Connections (invite, accept,
ignore, remove), posts (update, kudos, opening; announcements by HR/admin; company-only or network-wide; likes), direct
messages with unread counts.

### 3.15 Smart suggestions

A ranked list on the dashboard built from live data, each with a next step: overdue AR (largest balance × days late),
consultants who didn't submit, timesheets waiting, pay-when-paid invoices now releasable, vendor mismatches, approved
hours not invoiced, SOWs near ceiling or end, unsigned envelopes, missing/expiring documents, registrations waiting,
consultants rolling off. Amounts only for finance. Optional *Ask* box answers questions in plain English using only
these items (requires an Anthropic API key; nothing else is sent).

### 3.16 Users, security and audit

- Invite by e-mail with role, title, reporting line (org hierarchy), approval limit; vendor/client users are tied to
  their company, consultant users to their record. Lock, deactivate, withdraw invitations; a workspace always keeps one
  active admin and admins can't demote themselves.
- Account & security: change password (12+ characters), authenticator apps, sign out other devices, preferences
  (density, time zone), e-mail preferences.
- Audit log: every insert/update/delete with who, role, time, IP, device and field-level before/after; filter by record
  type, dates, person or value; export.

## 4. Notifications catalog

| Event | To | When |
|---|---|---|
| Invitation | Invitee | On invite |
| Registration received / decided | Applicant | On submit / decision |
| Workspace ready | First admin | On approval / creation |
| Timesheet reminder | Consultant (+HR on Tuesday) | Fri, Mon, Tue |
| Invoice sent | Customer contact | On send |
| AR courtesy / overdue | Customer contact (+finance at 30 days) | −7, +1, +7, +15, +30 days |
| Contract ending | Legal and admins | 90/60/30 days before |
| Document expiring | Person, HR, extra recipients, company contact | 120/90/60/30/14/7/0 days, then weekly |
| Policy to accept | Consultant | 0/7/14 days after effective |
| Signature request / reminder / code / declined / completed | Signer / sender / everyone | As they happen; reminders every N days |

All scheduled e-mails are de-duplicated, so a re-run never sends twice.

## 5. Glossary

**AR** accounts receivable — money owed to you. **AP** accounts payable — money you owe. **C2C** corp-to-corp — the
consultant is employed by a vendor that bills you. **1099** independent contractor paid directly. **W-2** your employee.
**MSA** master services agreement. **SOW / work order** the assignment-level contract under an MSA.
**Pay-when-paid** you pay the vendor only after your customer pays you. **Three-way match** invoice vs approved hours vs
contract rate. **ESIGN / UETA** US laws that give electronic signatures legal effect. **I-9** employment eligibility
verification form; **E-Verify** the online confirmation system; **EAD** employment authorization document.
