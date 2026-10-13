# myTrakIn user manual

Version 1.0 · October 2026

This manual is organised by what you do. Find your role in the table, then read **Getting started** and your sections.

| I am… | Read |
|---|---|
| Everyone | [1 Getting started](#1-getting-started), [2 Finding your way](#2-finding-your-way-around), [14 Profile & network](#14-your-profile-and-the-network), [15 Account & security](#15-account-and-security) |
| Admin | All sections, especially [3 Setting up](#3-setting-up-a-workspace-admins), [12 Users](#12-users-and-roles-admins), [13 Import](#13-import-and-export) |
| Finance | [4 Dashboard](#4-dashboard), [5 Payment flow](#5-payment-flow), [6 Invoices](#6-invoices-and-payments), [7 Payroll, 1099, referrals](#7-payroll-1099-and-referrals) |
| Account manager | [4](#4-dashboard), [8 Companies](#8-clients-and-vendors), [9 Consultants & placements](#9-consultants-projects-and-placements), [10 Contracts & e-signatures](#10-contracts-and-e-signatures) |
| HR / Legal | [9](#9-consultants-projects-and-placements), [10](#10-contracts-and-e-signatures), [11 Compliance](#11-compliance) |
| Approver | [6.1 Approving timesheets](#61-approving-timesheets) |
| Consultant | [16 Consultant guide](#16-consultant-guide) |
| Vendor or client | [17 Vendor and client guide](#17-vendor-and-client-guide) |
| Platform owner | [18 Owner console](#18-owner-console) |

---

## 1. Getting started

### Signing in
1. Open the address your company gave you (for example `https://app.yourcompany.com`).
2. Choose a sign-in method:
   - **E-mail me a code** — enter your e-mail, then the 6-digit code from the e-mail (valid 10 minutes). No password needed.
   - **Company single sign-on** — enter your work e-mail; you're sent to your company's login (Okta, Entra ID, Google Workspace…).
   - **Google** or **Microsoft** — use those accounts.
   - **Text me a code** — after you've added and verified your mobile under *Account & security* (if your company enabled it).
   - **Use a password** — if you set one under Account & security.
3. Use the e-mail address you were invited with. If you see *Almost there*, nobody has invited that address yet —
   ask your administrator.

### Two-step verification
Admins and finance users must add an authenticator app the first time:
1. Install Google Authenticator, Microsoft Authenticator, 1Password or Authy on your phone.
2. Scan the QR code shown after sign-in (or type the key under it).
3. Enter the 6-digit code from the app. From now on you'll be asked for a code at each sign-in.

Lost your phone? Ask another admin; they can't see your codes but the platform owner can reset your factor through
Supabase (see the operations runbook).

## 2. Finding your way around

- **Left menu** — only the sections your role can use. On a phone, tap ☰.
- **Top bar** — the workspace name (a drop-down if you belong to several companies), the theme button
  (Auto → Dark → Light) and your name (profile, account & security, sign out).
- **Every list** has: a search box (searches all columns), filters for key columns, click a column header to sort
  (click again to reverse), **List / Cards** views (your choice is remembered), **Export** (CSV of exactly what you see),
  and *Show more* after 50 rows. Many lists also have **Template / Import / Export all**.
- **Status colours** — green done/paid, blue open/in progress, amber waiting/on hold, red overdue/failed/missing,
  violet out for signature.
- **Masked values `••••`** mean the amount exists but isn't yours to see (another link in the chain, or not your role).

## 3. Setting up a workspace (admins)

Open **Workspace settings**. The setup checklist has eight steps; click *Mark … done* as you finish each.

1. **Company details** — legal name, EIN, state.
2. **Invite your team** — Users & roles → *Invite user* (see section 12).
3. **Clients & vendors** — add them or import the template (section 13).
4. **Import existing data** — consultants (including former), MSAs, SOWs with amounts invoiced so far, placements and
   rates, open invoices, payroll history.
5. **MSAs & SOWs** — record signed contracts and attach PDFs, or send new ones for e-signature.
6. **Projects & placements** — who works where, at which bill and pay rate.
7. **Policies & reminders** — publish policies (Compliance → Policies) and review reminder rules (Compliance → Reminders).
8. **Go live** — the workspace becomes *Active*.

Also in settings: which sign-in methods are allowed, your SSO domain, MFA for all staff, idle sign-out and the invoice footer.

## 4. Dashboard

- **KPIs** — AR outstanding, overdue AR, collected in the last 30 days, AP outstanding and on hold (finance only),
  contracts ending soon.
- **Smart suggestions** — the most important things to do now, ranked, each with a button that takes you there.
  Type a question in **Ask** (if enabled), e.g. *"What should finance do first today?"*
- **Cash in and out** — what customers owe by due week, and what you'll pay out, for six weeks.
- **Needs attention** — overdue invoices, vendor mismatches, held payables, SOWs near their ceiling, MSAs expiring,
  documents expiring. Click a line to open it.
- **Timesheets missing for last week.**

## 5. Payment flow

One row per consultant and period. Read it left to right:

- Dashed card **End client → customer** — not your contract: shown by name, amount masked, not tracked.
- **Customer → you (AR)** — your invoice, amount, status, due date. Click to open.
- **You → payee (AP)** — the vendor's or contractor's invoice, or *W-2 payroll*.
- **Gap AR − AP** on the right.

Use **Open / All** and the search box. Colours follow the legend at the top.

## 6. Invoices and payments

### 6.1 Approving timesheets
1. **Timesheets** → pick the week with ← → (weeks run Sunday–Saturday).
2. The *Checks* column summarises each timesheet: *All checks pass*, *n to review* or *n failed*.
3. Click a row to review: hours per project per day, every check with its detail, and (finance) the AR and AP amounts
   approval will create.
4. **Approve**, or **Return for changes** with a message the consultant will see.
5. For clean weeks use **Approve all that pass** — only timesheets with no warnings are approved.

The **History** tab lists every week, consultant and project with filters.

### 6.2 Creating and sending client invoices
1. **Invoices** → **Create invoices from timesheets** → choose the period → *Create drafts*.
   Hours already invoiced are skipped, so you can run it again safely.
2. Open each draft, check it, and click **Send to customer** (e-mails the company's contact; the due date follows the terms).
3. To invoice something by hand (a fixed fee, a correction), use **New client invoice**: placement, period, hours, PO and memo.

### 6.3 Recording payments
Open the invoice → *Payments* → amount, date, method, reference → **Record payment**. Part payments are fine. When a
client invoice is paid in full, any **pay-when-paid** vendor invoice waiting on it becomes *Ready to pay*.

### 6.4 Following up
Add **follow-up notes** on the invoice ("Called AP, payment run Friday"). Automatic reminders go to the customer 7 days
before the due date and 1, 7, 15 and 30 days after (finance copied at 30).

### 6.5 Vendor and 1099 invoices
- Vendors submit invoices in their portal; you can also see them under **Invoices → Vendor & 1099 invoices (AP)**.
- **Exception** = the hours don't match approved timesheets. Open it: the *three-way match* shows invoiced, approved and
  billed hours. **Accept at approved hours** recalculates the amount, or ask the vendor for a corrected invoice.
- **Held** = pay-when-paid, waiting for your customer.
- **Payment run** (AP tab) — tick the invoices to pay, choose ACH/Wire/Check and the date, **Record**. Held and
  mismatched invoices are left out automatically.
- **Void** an invoice (with a reason) only if it has no payments.

## 7. Payroll, 1099 and referrals

**W-2 payroll** — add each pay-run line or import the *W-2 payroll* template from your payroll provider's report.
Employer taxes and benefits give the true cost of each employee.

**Referral fees**
1. *New referral agreement* — referrer, type (individual 1099, company, employee), the referred consultant, hourly fee
   (with optional hour cap) or one-time fee, eligible-from date, W-9 on file.
2. The table shows *Earned* (from approved hours or the one-time fee once due), *Paid* and *Due*.
3. **Pay** records a payment. Individuals need a W-9 first — click *Mark received* when you have it.

**1099 summary** — choose the tax year. Everyone paid as a 1099 contractor or individual referrer, the total paid,
W-9 status and whether a 1099-NEC is needed (threshold shown at the top). Export it for your tax preparer.

**Expenses** — approve or reject what consultants submitted; finance marks approved expenses *Reimbursed*.
**Time off** — approve or decline requests.

## 8. Clients and vendors

- **Add company** — legal name, type (client, prime vendor, vendor, end client), payment terms, EIN, state, contact
  (the contact's e-mail receives invoices and reminders).
- The company page shows onboarding stages (*Mark … done*), details, agreements, SOWs with how much is used, tracked
  documents and **Files** (drag in W-9s, COIs, anything up to 25 MB).
- **Mark inactive** (with a reason) when you stop working together; history stays. **Reactivate** any time.
- Old and inactive vendors and clients can be imported in bulk (section 13).

## 9. Consultants, projects and placements

### Onboarding someone
1. **Consultants → Onboard someone**.
2. Pick the type: **W-2 employee (full-time)**, **W-2 contract**, **C2C (through a vendor)** or **1099 contractor**.
3. Name, e-mail, start date (and employer for C2C) → *Start onboarding*. They receive a sign-in invitation.
4. On their page, tick the checklist as items are done (offer signed, I-9, E-Verify, W-4, NDA…).
5. **Finish onboarding** when the list is complete — the consultant becomes Active and can enter time.

### While they work
- **Edit** contact details, skills, and (HR) work authorization, I-9 and E-Verify status.
- Projects, agreements, policy acceptances (with time and IP), tracked documents and files are all on their page.

### When they leave
**Offboard** → last day, reason, eligible for rehire. All assignments end, sign-in stops, nothing is deleted. They move to
the **Former** tab. **Rehire** restarts onboarding.

### Projects and placements
- **New project** — code, name, client, prime vendor (if you're a sub), dates, client approver.
- **New placement** — consultant, project, role, hours/week, dates, end client (name only), who you bill (AR customer,
  SOW, bill rate, terms) and who you pay (vendor or 1099, SOW, pay rate, terms, pay-when-paid). W-2 employees have no
  AP payee. A consultant can have as many placements as needed.

## 10. Contracts and e-signatures

### Recording or creating an agreement
**MSAs & SOWs → Add agreement**:
- *Already signed (record it)* — for contracts signed outside myTrakIn; attach the PDF on the agreement page.
- *New draft (send for signature)* — then **Send for signature** from the agreement page.

**Add SOW** — under an agreement, side (we bill / we pay), dates, value ceiling, amounts invoiced and collected before
myTrakIn, and (for vendor SOWs) the client SOW it supports.

**Amend / extend** — on the SOW page, describe the change, new end date and value change → draft → *Send* for signature.
The SOW updates automatically when everyone signs.

The **Missing & expiring** tab lists every gap: companies without an MSA, consultants without NDA/offer/contractor
agreement, policies not accepted, documents missing or expiring.

### Sending a document for signature
1. **E-signatures → Send a document** (or *Send for signature* on an agreement, SOW or amendment).
2. Title, PDF, signers in order (name, e-mail, company), *Sign in order* on/off, message.
3. **Send now** (or *Save draft*).
4. Follow progress on the envelope page: each signer's status and the audit trail with time, IP address and location.
   **Remind now**, **Void**, **View document** / **Download signed PDF**.

## 11. Compliance

- **Expiring documents** — *Track a document* (person, type, label, expiry date, what it holds, extra recipients).
  Click a row to **Record renewal** with the new date. E-mails go out automatically before and after expiry.
- **Work authorization & I-9** — every non-former consultant with authorization type, valid-until, I-9 and E-Verify
  status and a plain-language finding.
- **Policies** — *Publish policy* (name, version, effective date, PDF, who must accept). Click a policy to see who
  accepted, when, and from which IP address.
- **Registrations** — copy your public registration link and send it to new vendors, clients and contractors. Review each
  registration: details, automatic checks, possible duplicates, documents. **Approve**, **Ask for more** or **Reject**.
- **Reminders & e-mails** — (admins) switch reminder rules on/off and change their days. Below, the log of every e-mail sent.

## 12. Users and roles (admins)

**Invite user** — e-mail, role (the list explains each), company (vendor/client users) or consultant record
(consultant users), title, reports to, approval limit. Click a user to change role, title, manager, limit or access
(Active, Locked, Deactivated), or to withdraw a pending invitation. A workspace always keeps at least one active admin.

**Audit log** — filter by record type, dates or a person/value; click a line to see before/after values, IP and device;
*Export CSV* for auditors.

## 13. Import and export

1. **Import & export** → choose what you're importing → **Download template** (it contains sample rows — delete them).
2. Fill it in Excel or Google Sheets. Dates as `YYYY-MM-DD`. Required columns are marked *.
3. Save as **CSV** → choose the file → **Check file**. Fix any lines listed and check again.
4. **Import**. Rows that still fail are listed; the others are saved. Re-importing the same file updates existing rows.

Order for a new workspace: clients & vendors → consultants → agreements → SOWs → projects → placements → invoices →
documents → payroll → users.

**Export** any data set as CSV in the same columns, so you can edit and re-import.

## 14. Your profile and the network

- **My profile** (top-right menu) — *Change photo*, *Change cover*, *Edit profile*: headline, location, about,
  experience, skills, website, open to work, who can see your profile, whether connections see your e-mail and phone.
  Your profile is yours and moves with you if you work with another company on myTrakIn.
- **Network → Feed** — post updates, kudos and openings to your company or the whole network; like posts.
- **People** — search by name, skill, title or city; *Connect*.
- **Connections** — accept or ignore invitations; message connections.
- **Messages** — conversations with unread counts.

## 15. Account and security

**Account & security** (top-right menu): add your mobile for text-message sign-in, set or change a password (12+ characters, letters and numbers), add or remove
authenticator apps, **Sign out of all other devices**, table density, time zone, and which e-mails you want.
Legal and compliance notices are always sent.

## 16. Consultant guide

- **My work** — your projects (any number), the chain for each (who pays whom — names only), SOW end dates and
  extensions in progress, your work authorization, and **Where my payments are**: for each period, whether the
  customer has paid and whether your employer (or you, for 1099) has been paid — status and dates only.
- **My timesheet** — enter hours per project per day (quarter hours), add internal time if needed, **Save draft**,
  **Submit week** by Friday. Returned weeks show the reason; fix and submit again. History below — click a week to open it.
- **Policies & documents** — read each policy and click **Accept** (time and IP are recorded); see your agreements
  and offers, and the documents we track for you with their expiry dates.
- **Expenses & time off** — submit expenses (keep receipts) and request time off; decisions appear in the lists.
- **Signing documents** — you'll receive an e-mail link. Confirm your e-mail with the code, agree to sign
  electronically, read, type or draw your signature, and sign. The completed PDF is e-mailed to you.

## 17. Vendor and client guide

**Vendors** see their invoices to us, their consultants' placements with the agreed pay rate, and their consultants'
timesheets. **Submit an invoice**: your number, the placement, period and hours (invoice approved hours only). The
amount is calculated from the agreed rate. Status: *Received* (matches), *Exception* (hours differ — AP will contact
you), *Held* (pay-when-paid, waiting for our client), *Ready to pay*, *Scheduled*, *Paid*.

**Clients** see invoices addressed to them and their placements' bill rates.

Both can use the network and their profile.

## 18. Owner console

For the company running myTrakIn. **Owner console** shows all workspaces, active users, MRR/ARR, revenue per user, new
workspaces, sign-ups waiting and inactive workspaces.
- **Sign-up requests** — open one, review the checks, **Approve & create workspace** (the contact becomes its admin and
  gets an invitation), **Ask for more** or **Reject**.
- **Create workspace** — directly, with plan, trial and first admin.
- Click a workspace to change plan, status (Suspended blocks sign-in; Closed ends it) or the trial end date.

## 19. Troubleshooting

| Problem | What to do |
|---|---|
| "No workspace has invited this address" | Sign in with the invited e-mail, or ask your admin to invite this one. |
| Code e-mail didn't arrive | Check spam; wait one minute and *send a new code*; codes expire after 10 minutes. |
| "Finish two-step verification" | Your role needs an authenticator app — follow the on-screen steps. |
| "Not available for your role" | Ask an admin if you need that access. |
| A timesheet can't be edited | It's submitted or approved — ask your approver to return it. |
| Import says "column missing" | Download the template again; don't rename headers. |
| A signing link "doesn't work" | It was used, voided or expired — ask the sender to remind you (a new link is sent). |
| Amount shows `••••` | It belongs to another link of the chain or your role can't see it — by design. |
