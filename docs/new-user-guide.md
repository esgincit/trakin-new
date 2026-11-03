# myTrakIn new user guide

Version 1.0 · November 2026 · For every new user, whatever your starting point.

This guide explains, module by module, what you see and exactly what to click. It is written in three
independent tracks so you never have to read instructions that don't apply to you:

| Your starting point | Read | What you are |
|---|---|---|
| **Individual user** | [Part A](#part-a--individual-user) | You have a myTrakIn account but no company workspace of your own. You can build a profile, use the network, create or join a company, and — if a company places you — submit timesheets, read policies, request time off and track payments. |
| **Company user** | [Part B](#part-b--company-user) | You work inside an enrolled company workspace (admin, finance, account manager, legal, HR, approver, viewer, vendor, client or consultant). |
| **Platform admin** | [Part C](#part-c--platform-admin) | You run myTrakIn itself: you review company sign-ups, create and manage workspaces, and watch platform usage and revenue. |

If you are not sure which track you are on: open the app. A left menu with **Dashboard / Invoices / Projects**
means you are a company user. A menu with only **Network / My companies / My profile** means you are an
individual user. A **Platform admin** entry means you are platform staff.

> **One account, many companies.** The same login works in every company that invites you. Use the workspace
> selector at the top of the screen to switch between your company, a vendor portal and a client portal.

---

## Contents

- [0. Shared basics](#0-shared-basics)
- [Part A — Individual user](#part-a--individual-user)
  - [A1. Create your account](#a1-create-your-account)
  - [A2. Your profile](#a2-your-profile)
  - [A3. Network](#a3-network)
  - [A4. My companies](#a4-my-companies)
  - [A5. Account & security](#a5-account--security)
  - [A6. When a company places you (consultant self-service)](#a6-when-a-company-places-you-consultant-self-service)
  - [A7. When a company invites you as a vendor or client](#a7-when-a-company-invites-you-as-a-vendor-or-client)
  - [A8. Individual user troubleshooting](#a8-individual-user-troubleshooting)
- [Part B — Company user](#part-b--company-user)
  - [B0. Your first day](#b0-your-first-day)
  - [B1. Setup checklist](#b1-setup-checklist)
  - [B2. Company settings](#b2-company-settings)
  - [B3. Users & roles](#b3-users--roles)
  - [B4. Dashboard](#b4-dashboard)
  - [B5. Clients & vendors](#b5-clients--vendors)
  - [B6. Consultants & onboarding](#b6-consultants--onboarding)
  - [B7. Projects & placements](#b7-projects--placements)
  - [B8. MSAs & SOWs](#b8-msas--sows)
  - [B9. E-signatures](#b9-e-signatures)
  - [B10. Timesheets](#b10-timesheets)
  - [B11. Invoices](#b11-invoices)
  - [B12. Payment flow](#b12-payment-flow)
  - [B13. Payroll, 1099 & referrals](#b13-payroll-1099--referrals)
  - [B14. Compliance](#b14-compliance)
  - [B15. Import & export](#b15-import--export)
  - [B16. Audit log](#b16-audit-log)
  - [B17. Roles & permissions (owner)](#b17-roles--permissions-owner)
  - [B18. Partner portal (vendor and client)](#b18-partner-portal-vendor-and-client)
  - [B19. Company user troubleshooting](#b19-company-user-troubleshooting)
- [Part C — Platform admin](#part-c--platform-admin)
  - [C1. Access and security](#c1-access-and-security)
  - [C2. Platform admin console](#c2-platform-admin-console)
  - [C3. Reviewing a company sign-up](#c3-reviewing-a-company-sign-up)
  - [C4. When a customer needs a workspace](#c4-when-a-customer-needs-a-workspace)
  - [C5. Managing a workspace](#c5-managing-a-workspace)
  - [C6. Platform admins](#c6-platform-admins)
  - [C7. Platform boundaries](#c7-platform-boundaries)
  - [C8. Platform troubleshooting](#c8-platform-troubleshooting)
- [Appendix 1 — The end-to-end workflow](#appendix-1--the-end-to-end-workflow)
- [Appendix 2 — Status meanings](#appendix-2--status-meanings)
- [Appendix 3 — Module map by audience](#appendix-3--module-map-by-audience)

---

## 0. Shared basics

### 0.1 Signing in

1. Open the address your company or the platform team gave you (for example `https://app.yourcompany.com`).
2. Choose a sign-in method:
   - **E-mail me a code** — enter your e-mail, then the 6-digit code from the e-mail (valid 10 minutes). No password needed.
   - **Company single sign-on (SSO)** — enter your work e-mail and continue to your company's identity provider.
   - **Google** or **Microsoft** — use those accounts.
   - **Text me a code** — after adding a mobile number under **Account & security**.
   - **Use a password** — if you set one.
3. Use the e-mail address you were invited or registered with. If the app says no workspace has invited that
   address, ask your administrator to invite it (individual users can still use the network and create a company).

Admins and finance users must add an authenticator app the first time. Everyone else can turn on two-step
verification from **Account & security**.

### 0.2 Navigation

- **Left menu** — only the modules your role can open. On a phone, tap **☰**.
- **Top bar** — workspace selector (if you belong to more than one company), theme button (Auto → Dark → Light),
  and your name menu: **My profile**, **Account & security**, **Sign out**.
- **Every list** has search, column filters, column sorting, **List / Cards**, **Export**, and **Show more** after
  50 rows. Many lists also have **Template / Import / Export all**.
- **Colours** — green done/paid/active, blue open/in progress, amber waiting/on hold, red overdue/failed/missing,
  violet out for signature.
- **`••••`** means an amount exists but is not yours to see (another link in the chain, or your role is not
  allowed to see money).

### 0.3 The one workflow every company follows

```
Register → Verify → NDA → MSA → Project → SOW → Acceptance
        → Resource contract → Acceptance → Timesheet → Invoice → Payment → Confirmation
```

Different roles own different steps. The platform does not replace the work; it records each step, checks the
one before it, and shows where everything is.

### 0.4 AR and AP — the only two links myTrakIn tracks

- **AR (accounts receivable)** — what the customer owes **your company**. You bill it.
- **AP (accounts payable)** — what **your company** owes a vendor or contractor. You pay it.
- The layer above you (end client → your customer) and the layer below your vendor are shown **by name**, with
  `••••` instead of amounts, and are never stored by you.
- A **project** is the work. A **placement** puts one consultant on one project with your AR and AP terms.

### 0.5 Roles inside a company

| Role | Label in the app | Best for |
|---|---|---|
| `tenant_admin` | Admin | Running the workspace, users, settings, every module |
| `finance` | Finance | Invoices, payments, rates, payroll, 1099s, payment runs |
| `account_manager` | Account manager | Clients, projects, placements, contracts, AR |
| `legal` | Legal | Agreements, e-signatures, audit, compliance |
| `hr` | HR | Onboarding, I-9/work authorization, policies, documents |
| `approver` | Approver | Timesheet approval, expense/time-off approval |
| `viewer` | Viewer | Read-only access to what the base role could see |
| `vendor_admin` | Vendor | Partner portal: own consultants, timesheets, AP invoices |
| `client_user` | Client | Partner portal: invoices addressed to them, projects, history |
| `consultant` | Consultant | Self-service: My work, My timesheet, documents, requests |

A company **owner** (shown as **Owner** or **Co-owner**) is the person who controls roles and permissions. The
owner is always an admin; only the owner can create custom roles, change another person's access, or transfer
ownership. A **platform owner** (`super_admin`) is different: they run myTrakIn, not a customer company.

---

# Part A — Individual user

An individual user has a personal myTrakIn account. You do **not** need a company to register. Your menu shows
**Network**, **My companies**, **My profile** and **Account & security**. When a company invites or places you,
the company workspace appears in the top bar and the consultant or partner menu appears too.

## A1. Create your account

1. Open the app and choose **Create account** (or go to `/create-account`).
2. Enter your full name, e-mail and a password of at least 8 characters.
3. Choose **Create account**.
4. Open the confirmation e-mail (valid 24 hours) and follow the link.
5. Sign in. If the confirmation e-mail does not arrive, check spam and use **send it again**; if e-mail delivery
   is down, ask your administrator to create your account without e-mail.
6. You can also sign up with **Google** or **Microsoft** — the same account then works everywhere.

After signing in you land in the member area. No company is required.

## A2. Your profile

**Top-right name → My profile** (or **Network → My profile**).

1. **Change photo** / **Change cover** — upload an image.
2. **Edit profile** — headline, location, about, experience, skills, website, “open to work”.
3. Choose who can see your profile and whether connections see your e-mail and phone.
4. Save.

Your profile belongs to you, not to a company. It moves with you if you later work with another company on
myTrakIn.

## A3. Network

**Network** has four tabs.

1. **Feed**
   -  Write an update, kudos or job opening.
   -  Choose the audience: **Everyone in my network**, or a company workspace you belong to.
   -  Post. You can like posts and delete your own.
2. **People**
   -  Search by name, skill, title or city.
   -  Open a profile and choose **Connect**.
3. **Connections**
   -  Accept or ignore invitations.
   -  Open a connection and send a message.
4. **Messages**
   -  Read conversations and unread counts.
   -  Reply from the conversation.

Individual users can do all of this immediately, before joining any company.

## A4. My companies

**My companies** lists every business you created or belong to.

### Create your own company

1. Choose **Create your company**.
2. The wizard has four steps:
   - **US company:** W-9 upload → company details → e-mail verification → authorize & create.
   - **India company:** details & MOA → company details → e-mail verification → authorize & create.
3. Enter the legal name, business type, tax ID (EIN/SSN or CIN), address, company domain and company e-mail.
4. Verify the 6-digit code sent to the company e-mail. The company e-mail is where company-scoped mail goes —
   not necessarily your personal login.
5. Authorize and submit.
6. The myTrakIn team reviews the company. You are e-mailed when it is activated, needs more information, or is
   rejected. A rejected company can be corrected and resubmitted.

An unfinished company appears as **Unfinished company setup**. Use **Resume setup** to continue, or
**Discard draft** to throw it away. Nothing is sent for activation until you finish step 4.

### Join an existing company

- Ask the company admin to invite your e-mail from **Users & roles**.
- Open the invitation e-mail and sign in with that e-mail.
- The company appears in **My companies** and in the top-bar workspace selector.
- If you belong to several companies, switch with the top bar; each workspace has its own data and permissions.

Once your company is active, you are its owner and the **Part B** company modules become available to you.

## A5. Account & security

**Top-right name → Account & security.**

- **Mobile number** — add and verify it to sign in with a text-message code.
- **Password** — set or change it (12+ characters with letters and numbers).
- **Authenticator app** — add or remove a second factor.
- **Sign out of all other devices** — use this if you lose a device.
- **Table density**, **time zone**, and **e-mail preferences**.
- Legal and compliance notices are always sent and cannot be turned off.

## A6. When a company places you (consultant self-service)

When a company onboards you as a consultant, you receive an invitation. Sign in, select that company in the
top bar, and use the consultant menu.

### My work

- See every project you are placed on, your role, dates, hours per week, the governing SOW and its end date.
- See the chain for each project: end client → customer → the company that placed you → your employer (if any)
  → you. Names only — no rates or amounts.
- See **Where my payments are**: for each period, whether the customer has paid the placing company and whether
  you (or your employer) have been paid. Status and dates only.
- When the placing company records a payment to you, an **Acknowledge payment** button appears in the
  **Acknowledge** column. Click it once. The payment becomes **confirmed** and your acknowledgement date is shown.
  If the payment is still **pending** or **processing**, wait until it is **completed** and the button appears.
- W-2 employees see **Payroll** instead of a vendor/contractor payment.

### My timesheet

1. Choose the week (weeks run Sunday–Saturday).
2. Enter hours per project per day in quarter hours. Internal/non-billable time can be entered too.
3. Write the week's note — a note is required before any submission.
4. Choose **Save draft** to keep the week without sending it, or **Submit** next to a project's total.
5. Each project is submitted independently. A submitted or approved project is locked for that project only;
   other projects can still be edited.
6. A returned week shows the reason. Fix it and submit it again.
7. **History** below lists your weeks; click one to open it.

The system checks the resource contract (offer letter or work order), the client SOW acceptance, weekly
allocation and weekend confirmation before a week can be approved.

### Policies & documents

- Read each policy and choose **Accept**. The time and IP address are recorded.
- See your signed agreements and offers.
- See the documents the company tracks for you and their expiry dates.

### Signing a document

1. Open the signing link in the e-mail.
2. Confirm your e-mail with the one-time code.
3. Agree to sign electronically (ESIGN/UETA consent).
4. Read the document, then type or draw your signature.
5. Sign. The completed, sealed PDF is e-mailed to you and the company.

### Expenses & time off

**Expenses & time off** has two forms and two lists.

- **New expense** — date, amount, category, project (optional), billable yes/no. Submit. Keep the receipt;
  your approver may ask for it.
- **Request time off** — from/to dates, type (paid time off, sick, unpaid), note. Send.
- **My expenses** and **My time off** show the decision and status.

### What an individual/consultant cannot do

- See bill or pay rates and invoice amounts.
- Approve their own timesheet.
- Create invoices, contracts, projects or placements.
- Edit a submitted or approved project's hours (ask the approver to return the week).

## A7. When a company invites you as a vendor or client

The invitation puts you in that company's **vendor** or **client** portal. Your menu shows **Home** plus
**Network**.

### Vendor portal

1. **Home** lists the invoices you sent, the placements of your consultants, and their approved timesheets.
2. Choose **Submit an invoice**:
   - your invoice number;
   - the placement;
   - period start and end;
   - hours (invoice approved hours only).
3. Submit. The amount is calculated from the agreed rate.
4. Read the status:
   - **Received** — hours match the approved timesheets.
   - **Exception** — hours differ; the company's AP team will contact you.
   - **Held** — pay-when-paid, waiting for the end customer to pay.
   - **Ready to pay**, **Scheduled**, **Paid**.
5. Keep your PDF; the company may ask you for it separately.

### Client portal

1. **Home** lists invoices addressed to you and the people working on your projects.
2. Open an invoice to see the period, hours, amount, balance and status.
3. When your workspace is the end client on a placement, **Timesheets → History** lists the approved weeks and
   lets you open one read-only.

Both portals can use the network and their profile.

## A8. Individual user troubleshooting

| Problem | What to do |
|---|---|
| “No workspace has invited this address” | Sign in with the invited e-mail, or ask the company admin to invite this address. |
| Confirmation e-mail did not arrive | Check spam, wait a minute and resend. If delivery is down, ask an admin to create the account without e-mail. |
| Cannot see a company I joined | Use the top-bar workspace selector; ask the admin to check your invitation status. |
| Payment button does not appear | The payment is not **completed** yet, or it is already confirmed. Read **Where my payments are**. |
| Timesheet is locked | That project is submitted or approved. Ask the approver to return it. Other projects can still be edited. |
| Signing link does not work | It was used, voided or expired. Ask the sender to remind you — a new link is sent. |
| An amount shows `••••` | It belongs to another link of the chain or your role cannot see money. This is by design. |

---

# Part B — Company user

You are inside an enrolled company workspace. What you can open depends on your role. This part follows the
modules in the left menu, in the order a new company usually sets them up.

## B0. Your first day

1. Accept the invitation and sign in.
2. Use the top bar to choose the correct company (if you belong to more than one).
3. The left menu shows only your modules. If a page is read-only, your role or a custom permission limits edits.
4. Admins and finance users add an authenticator app at first sign-in.
5. If your company is still onboarding, the workspace shows the setup checklist and a limited menu until it is
   activated.

## B1. Setup checklist

**Company settings → Setup checklist** has eight steps. Each step has **Mark “… done”** when it is complete.

1. **Company details** — legal name, EIN, state.
2. **Invite your team** — **Users & roles → Invite user**.
3. **Add clients & vendors** — add them manually or import the template.
4. **Import existing data** — consultants (including former), agreements, SOWs with prior amounts, placements and
   rates, open invoices, payroll history.
5. **Add MSAs & SOWs** — record signed contracts and attach PDFs, or send new ones for signature.
6. **Projects & placements** — who works where, at which bill and pay rate.
7. **Policies & reminders** — publish policies and review reminder rules.
8. **Go live** — the workspace becomes active.

> If you are an individual user who created this company, you are the owner and can do every step.

## B2. Company settings

**Company settings** is available to admins.

- **Company** — display name, legal name, EIN, state. Save.
- **Sign-in & security** — allow e-mail code, text code, company SSO (SAML), Google, Microsoft and/or password;
  set the SSO domain; require two-step verification for every staff user (always on for admin and finance);
  idle sign-out hours; invoice footer. Save.
- **Workflow** — the four gates:
  - **Require NDA** — an NDA must be in force before an MSA with that company, and before a project goes active.
  - **Require MSA** — an MSA/subcontract/ICA must be active before a project goes active, before invoices are
    created, and before vendor payments.
  - **Require acceptance** — the resource contract and the client SOW must be accepted before timesheets can be
    approved.
  - **Require resource contract** — a timesheet needs the resource's work order (vendor/1099) or offer letter (W-2).
  - When a switch is on and the requirement is missing, the action is blocked with a message naming what to do
    (or how to turn the switch off).
- **Numbering** — templates for every code (project, SOW, invoice, envelope…). Placeholders are
  `{YEAR} {YY} {MM} {YYYYMM} {SEQ} {SEQ:4} {CLIENT} {PROJECT}`; every template needs `{SEQ}`.
- **Setup checklist** — see B1.

> Individual users cannot change company settings unless they created the company and are its owner.

## B3. Users & roles

**Users & roles** is for admins. Every change is in the audit log.

### Invite someone

1. Choose **Invite user**.
2. Enter their e-mail.
3. Choose a role. The list explains each role in plain language.
4. For **Vendor** or **Client**, choose their company. For **Consultant**, choose the consultant record.
5. Optionally set a title, who they report to and an approval limit.
6. Optionally tick **Also create their password login now** — use this when e-mail codes are unavailable; share
   the one-time password shown with the person.
7. Choose **Send invitation**.

### Change someone

1. Click the person in the list.
2. Change role, title, manager, approval limit or access (**Active**, **Locked**, **Deactivated**).
3. Choose whether two-step verification is offered.
4. Save.
5. A pending invitation can be withdrawn.

A workspace always keeps at least one active admin. The owner can **Transfer ownership** to another active staff
user; the current owner stays an admin but can no longer change roles and permissions or transfer ownership.

## B4. Dashboard

**Dashboard** is the first page for staff and client users.

- **KPIs** — AR outstanding, overdue AR, collected in the last 30 days, AP outstanding and on hold (finance only),
  and contracts ending soon.
- **Smart suggestions** — the most useful next actions, ranked, each with a button.
- **Ask** (if enabled) — type a question in plain English, for example “What should finance do first today?”.
- **Cash in and out** — what customers owe by due week and what you will pay out, for six weeks.
- **Needs attention** — overdue invoices, vendor mismatches, held payables, SOWs near their ceiling, MSAs expiring,
  documents expiring. Click a line to open it.
- **Timesheets missing for last week**.

Figures are live: they read directly from invoices, payments, timesheets and contracts.

> Individual users do not see the company Dashboard. Platform admins see platform-wide totals in Part C, never a
> customer's operational dashboard.

## B5. Clients & vendors

**Clients & vendors** is everyone you bill and everyone you pay, current and former.

### Add a company

1. Choose **New company**.
2. Complete the same four-step company wizard used in **My companies**: W-9 (US) or details & MOA (India) →
   company details → e-mail verification → authorize & create.
3. Enter the legal name, tax ID, address, company domain and the company contact e-mail.
4. Verify the 6-digit code sent to the company e-mail. That address receives company-scoped mail, including
   invoices and reminders.
5. Save. The company appears in **Clients & vendors** and on **My companies**.

### Company page

- **Onboarding stages** — tick each stage as it is done.
- **Details** — legal name, EIN, state, terms, contact.
- **Agreements** — MSAs, NDAs, subcontracts with effective/expiry dates.
- **SOWs** — value, invoiced and remaining, burn percentage.
- **Tracked documents** — W-9, COI, certificates and expiry dates.
- **Files** — drag in W-9s, COIs and other documents (up to 25 MB each).

**Mark inactive** (with a reason) when you stop working together; history stays. **Reactivate** any time.

> Individual users see only their own company profile from **My companies**. Platform admins see the company in
> the platform console with plan, status, users, MRR and aggregate invoiced/collected/paid figures.

## B6. Consultants & onboarding

**Consultants** holds W-2 employees, C2C/E2E consultants and 1099 contractors — onboarding, active and former.

### Onboard someone

1. Choose **Onboard someone**.
2. Pick the engagement type:
   - **W-2 employee (full-time)**
   - **W-2 contract**
   - **C2C (through a vendor)**
   - **1099 contractor**
3. Enter name, e-mail, start date and (for C2C) the employer company.
4. Choose **Start onboarding**. The person receives a sign-in invitation.
5. On their page, tick the checklist as items are completed (offer signed, I-9, E-Verify, W-4, NDA…). Tick each
   item once, or use **Select all** / **Select none**.
6. Choose **Finish onboarding** when every item is ticked. The consultant becomes **Active** and can enter time.

### While they work

- **Edit** contact details, skills, and (HR) work authorization, I-9 and E-Verify status.
- See projects, agreements, policy acceptances (time and IP), tracked documents and files.
- **Offboard** — last day, reason, eligible for rehire. Assignments end, sign-in stops, nothing is deleted.
- **Rehire** — restart onboarding for a former consultant.

### What must exist before a placement

The placement form checks the contract before creating anything:

- **W-2 full-time / W-2 contract** — an active offer letter assigned to that consultant record in your workspace.
- **1099 contractor** — an active offer letter issued by your company for that consultant.
- **C2C / E2E** — an active MSA or subcontract with the company you bill (the AR customer).

If the requirement is missing, placement creation is blocked and the message names the missing agreement. This
is intentional: it is the same check the timesheet gate would make later.

> **Individual user:** the consultant sees **My work**, **My timesheet**, **Policies & documents** and
> **Expenses & time off** in the company workspace. They never see rates, amounts or the onboarding checklist.
> **Platform admin:** see consultant and placement counts in the platform console; never edit a customer's people.

## B7. Projects & placements

**Projects & placements** has two tabs.

### New project

1. Choose **New project**.
2. Enter code (or leave blank for the next code), name, client, prime vendor (if you are a subcontractor), dates,
   client approver and status.
3. Status:
   - **Active** — the project goes live. With **Require NDA** / **Require MSA** on, an active project needs the
     customer's NDA and MSA first.
   - **Planned** — save a project whose NDA/MSA is not signed yet.
   - **Internal** — your own company's work; no customer agreement is required.
4. Save.

Project codes are globally unique. The same code cannot exist on two projects anywhere in myTrakIn, so placement
pickers never show duplicates.

### New placement

1. Choose **New placement**.
2. Choose the consultant, project, role, hours per week and dates.
3. The end client is filled from the project (name only; it is not your contract).
4. Fill the **AR side** — who you bill, the SOW/work order, bill rate and terms.
5. Fill the **AP side** — the vendor company or 1099 contractor, the SOW/work order, pay rate, terms and
   pay-when-paid.
   - W-2 employees are paid through payroll: leave the AP payee empty.
   - A consultant can have any number of placements.
6. Save. The contract gate runs before the placement is created.

### Change a placement

Open it and choose **Edit**. You can change dates, hours per week, status, bill/pay rate and terms. Only finance
can change rates. Every change is audited.

### Add a resource from a SOW

Open a SOW and add a resource. The same placement rules and contract gates apply.

> **Individual user:** the consultant sees the placement as a project in **My work**. **Platform admin:** the
> console counts active placements; it does not create or change them.

## B8. MSAs & SOWs

**MSAs & SOWs** has three tabs: **Agreements**, **SOWs & work orders**, **Missing**.

### Add an agreement

1. Choose **Add agreement**.
2. Choose the type:
   - **MSA (client or prime)**
   - **Subcontractor agreement (vendor)**
   - **Independent contractor agreement (1099)**
   - **NDA**
   - **Offer letter**
3. Choose the company or consultant it is with, and which side you are.
4. Enter effective date, expiry, payment terms, renewal, notice period and insurance requirements.
   For an NDA, the payment and insurance fields are hidden.
5. Choose **New draft (send for signature)** or **Already signed (record it)**.
6. Save.

With **Require NDA** on, an MSA or subcontract cannot be created until an NDA is in force between the two
companies. The NDA may have been recorded by either side, in either workspace.

### Add a SOW / work order

1. Open the agreement, or choose **Add SOW**.
2. Choose the side: **We bill** (client SOW) or **We pay** (vendor/contractor work order).
3. Enter title, dates, value ceiling, prior invoiced and prior collected.
4. For a vendor SOW, optionally choose the client SOW it supports.
5. Save.

A SOW needs an active NDA between the two companies — before it is created, and again before it is sent. The
error says exactly that if the NDA is missing, expired or still pending.

### SOW page

- **Send for signature** — draft SOWs; opens the e-signature flow.
- **Amend / extend** — describe the change, new end date and value change; send for signature.
- **Send again** — only for a SOW the other company turned down (requires a reason on their side).
- **Approve / Turn down** — only when the SOW was sent to your company and is waiting for your answer.
- A SOW created by another workspace is shown read-only from your side: terms to approve, no money and no edits.

### Expiry and the Missing tab

The status shown is the **effective** status: once the expiry date passes, the agreement shows **Expired** even
if the stored status still says active. Expired agreements stop gating dependent records. The **Missing** tab
lists companies whose only MSA has expired.

> **Individual user:** you receive offers, NDAs and contractor agreements to sign by e-mail; you see them under
> **Policies & documents**. You never create an agreement. **Platform admin:** the console shows company counts;
> agreement content stays with the customer.

## B9. E-signatures

**E-signatures** is the sender side. Opening an agreement, SOW or amendment and choosing **Send for signature**
starts here.

1. Choose **Send a document** (or start from the agreement/SOW page).
2. Enter a title.
3. Attach one or more PDFs (up to 10 documents, 100 MB in total).
4. Add signers in order: name, e-mail, company.
5. Choose **Sign in order** on or off, the message, and the reminder interval.
6. Choose **Send now** or **Save draft**.
7. On the envelope page:
   - follow each signer's status;
   - read the audit trail (time, IP address, location, device);
   - **Remind now**, **Void**, **View document**, **Download signed PDF**.

The signer:

1. opens the e-mail link;
2. confirms their e-mail with a one-time code;
3. agrees to sign electronically;
4. reads, types or draws a signature;
5. signs.

The completed PDF is sealed with a certificate of completion and e-mailed to the signers and the sender.

A SOW envelope checks the NDA gate at creation and again at send, so “Send for signature” cannot bypass a missing
NDA.

> **Individual user:** you are a signer, not a sender. **Platform admin:** platform staff do not open customer
> envelopes or documents.

## B10. Timesheets

**Timesheets** is the approval side. Weeks run Sunday–Saturday.

1. Use ← → to pick the week.
2. Read the **Checks** column:
   - *All checks pass* — ready to approve.
   - *n to review* — warnings that need a human decision.
   - *n failed* — a rule is broken.
3. Click a row to review:
   - hours per project per day;
   - every check and its detail;
   - finance also sees the AR and AP amounts the approval will create.
4. Choose **Approve** or **Return for changes**. A note of at least 3 characters is required for both.
5. For clean weeks choose **Approve all that pass**. Only weeks with no warnings are approved.
6. **History** lists every week, consultant and project, with filters and export.

The approval flow:

- The placing company approves first.
- When the end client is represented in the workspace (or in their own workspace), the end client approves next.
- The final approval generates the invoices (AR and AP) automatically.

The gate before submission/approval checks the resource contract and the client SOW acceptance, depending on the
workflow switches.

> **Individual user:** enter and submit your own week in **My timesheet**; never approve it. **Platform admin:**
> see timesheet counts in the console; do not approve customer work.

## B11. Invoices

**Invoices** has **Client invoices (AR)**, **Vendor & 1099 invoices (AP)** and **Credit notes**.

### Create invoices from approved timesheets

1. Choose **Create invoices from timesheets**.
2. Choose the period.
3. Choose **Create drafts**.
4. The system creates one client invoice per placement for the approved hours, plus the matching vendor or 1099
   payable.
5. Hours already invoiced are skipped, so running it twice is safe.
6. Open each draft, check it, and choose **Send to customer**.
7. The customer's company contact e-mail receives the invoice. The due date follows the terms.

### Create an invoice by hand

Choose **New client invoice** for a fixed fee or a correction: placement, period, hours, PO and memo. The amount
is hours × the placement bill rate.

### Record a payment

1. Open the invoice.
2. In **Payments**, enter amount, date, method and reference.
3. Choose **Record payment received** for AR, or **Record payment made** for AP.
4. Part payments are fine. When a client invoice is paid in full, any **pay-when-paid** vendor invoice waiting on
   it becomes **Ready to pay**.
5. **Confirm received** / **Confirm payment** closes the payment. A 1099 contractor can also acknowledge their own
   AP payment from **My work → Acknowledge payment**; the confirmation shows the name and date.

### Follow up

Add a **follow-up note** on the invoice (“Called AP, payment run Friday”). Automatic reminders go to the customer
7 days before the due date and 1, 7, 15 and 30 days after; finance is copied at 30 days.

### Vendor and 1099 invoices (AP)

- Vendors submit invoices in their portal, or you can see them in the AP tab.
- **Exception** — the hours do not match approved timesheets. Open it: the **three-way match** shows invoiced,
  approved and billed-to-customer hours. Choose **Accept at approved hours** to recalculate, or ask the vendor for
  a corrected invoice.
- **Held** — pay-when-paid, waiting for your customer.
- **Payment run** — tick the invoices, choose ACH/Wire/Check and the date, and record. Held and mismatched
  invoices are left out automatically.
- **Void** an invoice with a reason only when it has no payments.
- **Credit notes** lower what a customer owes; a fully credited invoice counts as settled and releases
  pay-when-paid vendor invoices.

### 1099 payable and acknowledgement

For a 1099 contractor, the approval of the week creates the AP invoice to the contractor. The placing company
records the payment (in the AP invoice or a payment run). The contractor then sees **Acknowledge payment** on
**My work** and confirms it. The payment becomes **confirmed**.

> **Individual user:** consultants see status and dates only — never amounts. **Vendor:** submit and track
> invoices in the partner portal. **Platform admin:** see aggregate invoiced/collected/paid in the console.

## B12. Payment flow

**Payment flow** shows one row per consultant and period, left to right:

- **End client → customer** — dashed card; not your contract. Names only, amount masked.
- **Customer → you (AR)** — your invoice, amount, status, due date. Click to open.
- **You → payee (AP)** — the vendor or contractor invoice, or **W-2 payroll**.
- **Gap AR − AP** — the margin on that row.

Use **Open / All** and the search box. The legend at the top explains the colours.

> **Individual user:** the same information is on **My work → Where my payments are**, with status and dates only.
> **Platform admin:** the console shows platform-wide money totals and trend, not individual customer rows.

## B13. Payroll, 1099 & referrals

**Payroll, 1099 & referrals** has tabs based on your role.

### W-2 payroll (finance)

1. Run payroll in your payroll provider.
2. Import the payroll report, or choose **Add pay run line**.
3. Enter employee, period, pay date, hours, gross, employer taxes, benefits and net.
4. Save. The true employer cost is then included in margins and cash flow.

### 1099 summary (finance)

1. Choose the tax year.
2. Review everyone paid as a 1099 contractor or individual referrer: total paid, W-9 status and whether a
   1099-NEC is needed (threshold at the top).
3. Export the summary for your tax preparer.

### Referral fees (finance / HR)

1. Choose **New referral agreement**.
2. Enter the referrer (individual 1099, company or employee), the referred consultant, the fee (hourly with an
   optional hour cap, or one-time), the eligible-from date and whether a W-9 is on file.
3. The table shows **Earned**, **Paid** and **Due**.
4. Choose **Pay** to record a payment. An individual needs a W-9 first — use **Mark received** when you have it.

### Expenses (finance / HR / approver)

- Review what consultants submitted.
- Approve or reject.
- Finance marks approved expenses **Reimbursed**.

### Time off (HR / approver / account manager)

- Approve or decline requests.
- The consultant sees the decision on **Expenses & time off**.

> **Individual user:** submit expenses and time off from **Expenses & time off**; read the decision there.
> **Platform admin:** no access to a customer's payroll or people records.

## B14. Compliance

**Compliance** has five tabs.

### Expiring documents

1. Choose **Track a document**.
2. Choose the person or company, document type, label, expiry date, what it holds and any extra recipients.
3. Save. Reminders go to the person, HR and extra recipients 120, 90, 60, 30, 14 and 7 days before expiry, on
   the day, and weekly after until renewed.
4. Click a row to **Record renewal** with the new date.

### Work authorization & I-9

See every non-former consultant with authorization type, valid-until date, I-9 and E-Verify status and a
plain-language finding. HR updates the record.

### Policies

1. Choose **Publish policy**.
2. Enter name, version, effective date, PDF and who must accept.
3. Click a policy to see who accepted, when, and from which IP address.

### Registrations

1. Copy your public registration link and send it to new vendors, clients and contractors.
2. Review each registration: details, automatic checks, possible duplicates, documents.
3. Choose **Approve**, **Ask for more** or **Reject**.

### Reminders & e-mails

Admins switch reminder rules on/off and change their days. Below is the log of every e-mail sent.

> **Individual user:** read and accept policies under **Policies & documents**; the company tracks your documents
> and work authorization. **Platform admin:** the console sees company status and documents only during
> activation review.

## B15. Import & export

**Import & export** is for finance, HR and legal roles.

1. Choose what you are importing and choose **Download template**. Delete the sample rows.
2. Fill it in Excel or Google Sheets. Dates are `YYYY-MM-DD`. Required columns are marked `*`.
3. Save as **CSV** and choose **Check file**. Nothing is saved yet.
4. Fix the listed lines and check again.
5. Choose **Import**. Rows that still fail are listed; the others are saved. Re-importing the same file updates
   existing rows instead of duplicating them.

A new workspace imports in this order: clients & vendors → consultants → agreements → SOWs → projects →
placements → invoices → documents → payroll → users.

Where a row references a company or person, prefer the stable ID — a company by its Business ID (`C-0006`) and a
person by their ID (`U000123`) — over names. Both are accepted; exports lead with the ID.

**Export** any data set as CSV in the same columns, so you can edit and re-import.

> **Individual user:** not available. **Platform admin:** no access to a customer's import/export.

## B16. Audit log

**Audit log** (legal and finance) records every create, change and delete.

1. Filter by record type, dates, person or value.
2. Click a line to see the before and after values, IP address and device.
3. Choose **Export CSV** for auditors.

The log cannot be edited.

## B17. Roles & permissions (owner)

Only the company owner can open **Roles & permissions**.

1. Choose **New role**.
2. Name it and choose the base role (Finance, Account manager, Legal, HR, Approver, Viewer, Admin, Vendor,
   Client, Consultant).
3. For each module choose **Hidden**, **View** or **Edit**. A custom role can only narrow what the base role
   allows, never widen it.
4. Save.
5. On **Users & roles**, open a person and choose the custom role and any per-person exceptions.

Use this for roles like “Finance — view only” or “HR — no payroll”.

## B18. Partner portal (vendor and client)

Vendor and client users have a smaller menu: **Home** (their company name) and **Network**.

### Vendor

- See invoices you sent, placements of your consultants, and their approved timesheets.
- **Submit an invoice** — invoice number, placement, period, hours. The amount comes from the agreed rate.
- Statuses: **Received**, **Exception**, **Held**, **Ready to pay**, **Scheduled**, **Paid**.
- Invoice only approved hours. Attach your PDF after submitting if requested.

### Client

- See invoices addressed to you and the people working on your projects.
- Open an invoice for period, hours, amount, balance and status.
- When your company is the end client on a placement, **Timesheets → History** shows approved weeks; open one
  read-only.

Both can use the network and their profile.

## B19. Company user troubleshooting

| Problem | What to do |
|---|---|
| “No workspace has invited this address” | Sign in with the invited e-mail, or ask the admin to invite this one. |
| Code e-mail did not arrive | Check spam, wait a minute and resend; codes expire after 10 minutes. |
| “Finish two-step verification” | Your role requires an authenticator app — follow the on-screen steps. |
| “Not available for your role” | Ask an admin if you need that access; an owner can add a custom role. |
| A timesheet cannot be edited | It is submitted or approved. Only that project is locked; other projects can still be edited. |
| Import says “column missing” | Download the template again; do not rename headers. |
| “A signing link doesn't work” | It was used, voided or expired. Use **Remind now** on the envelope. |
| “An NDA in force with this company is needed first” | Create or renew the NDA with that company, or turn off **Require NDA** in Company settings → Workflow. The message names the expired/pending agreement. |
| “An active NDA is required between these companies before creating or sending an SOW” | Complete the NDA between the two companies, then create or send the SOW again. |
| “No active MSA — not invoiced” | Sign an MSA with the customer, or turn off **Require MSA** in Settings → Workflow. |
| Placement cannot be created | Check the consultant's contract: W-2 needs an active offer letter; 1099 needs an offer from your company; C2C/E2E needs an MSA/subcontract with the AR customer. |
| “No active offer letter is assigned to this consultant” | Assign the offer letter to that consultant record in this workspace, then create the placement. |
| End Client history is empty | Sign in as the end-client representative (`client` role) for the company that is the end client on the placement. |
| Hours reset after entering them | Choose **Save draft** or **Submit** before navigating away. |
| Only one project's Submit shows | Each project has its own **Submit** next to its total. Submit each project you want to send. |
| An amount shows `••••` | It is another link's money or your role cannot see it — by design. |

---

# Part C — Platform admin

Platform admins run myTrakIn. You do **not** work inside a customer's finance, HR or contracts; you manage
workspaces and the platform. Your menu shows **Platform admin** in addition to your own company workspaces.

## C1. Access and security

1. A platform admin must have signed in to myTrakIn at least once.
2. Another platform admin adds you from **Platform admin → Platform admins → Add platform admin**.
3. Use two-step verification. Platform access is the highest level in the product.
4. Keep the platform admin list small. Remove people when they leave the platform team.

## C2. Platform admin console

**Platform admin** has four tabs.

### Overview

- **KPIs** — total users, companies, MRR/ARR, revenue per user, active consultants, active placements.
- **Money moving through myTrakIn** — invoiced to clients, collected, outstanding from clients, paid to vendors
  (aggregate across the platform).
- **Onboarding pipeline** — where companies are in the activation journey; the “Waiting for activation” stage
  links to the queue.
- **Client invoicing and collections, last 12 months** — invoiced vs collected trend.
- **Subscription revenue by plan** — monthly revenue per plan.
- **Inactive companies** — companies with no activity for 14+ days.

### Companies

A list of every workspace: company, plan, status, users, consultants, MRR, invoiced, collected, paid to vendors,
last activity and created date. Click a row to open the workspace drawer.

### Waiting for activation

The sign-up queue. Click a company to review it (see C3).

### Platform admins

The list of platform staff. Add or remove admins here. You cannot remove yourself.

## C3. Reviewing a company sign-up

1. Open **Platform admin → Waiting for activation**.
2. Click the company.
3. Read:
   - owner name and e-mail;
   - business ID and company type;
   - legal name, DBA, tax ID (CIN for India, TIN for the US) and tax classification;
   - address, domain, company contact e-mail;
   - W-9 status and the W-9 file;
   - registration checks (with pass/warn/fail detail);
   - company documents and files.
4. If a document should be restricted (for example a government-issued ID), choose **Restrict**. Only the platform
   and the company's super admins can see it.
5. Upload a government document if you need it for the review.
6. Write a note to the owner. A note is required to **Ask for more info** or **Reject**.
7. Choose one:
   - **Activate** — the owner is e-mailed; the workspace becomes active.
   - **Ask for more info** — the owner is e-mailed the note and can correct the company and resubmit.
   - **Reject** — the owner is e-mailed the reason; the company can be corrected and resubmitted if allowed.
8. Read the **Still blocking** line before activating: it lists anything that must be resolved.

Activating also marks the W-9 you reviewed as verified.

## C4. When a customer needs a workspace

The console does not have a separate “create workspace” form. The path is:

1. The customer creates an account at **Create account**, then chooses **Create your company** and completes the
   four-step wizard (W-9 or details & MOA, company details, e-mail verification, authorize & create).
2. The company appears in **Platform admin → Waiting for activation**.
3. Review and activate it with the steps in C3.

If a customer cannot complete the wizard, help them through it — do not create a company inside their account
for them. Changing the plan, status, trial or owner afterwards is done in the workspace drawer (C5).

## C5. Managing a workspace

Open a company in **Companies**.

- **Status** — **Waiting for activation**, **Active**, **Suspended** (blocks sign-in), **Rejected** (owner can fix
  and resubmit), **Closed**.
- **Plan** — Starter, Growth, Enterprise.
- **Trial end date** — change it when a trial is extended.
- **Owner** — change the owner when the current owner has left. The new owner must already be an active user of
  that company.

Suspending is for abuse or non-payment. Closing ends the workspace. Neither deletes history.

## C6. Platform admins

1. Open **Platform admin → Platform admins**.
2. Choose **Add platform admin**.
3. Enter the e-mail of someone who has already signed in to myTrakIn.
4. They get the full console: every company, activation and analytics.
5. To remove someone, choose **Remove** next to their name. You cannot remove yourself.

## C7. Platform boundaries

Platform admins:

- Can see every workspace, its status, plan, usage and aggregate money.
- Can review company documents and restrict sensitive files.
- Can activate, suspend, close, change plan/trial and change the owner.
- **Cannot** approve a customer's timesheet, record their payments, edit their invoices, sign their contracts or
  change their payroll.
- Should not open customer e-signature documents or HR files unless the review requires it.

If a customer needs help with an operational step, fix the workspace lifecycle (status, owner, plan) or ask them
to follow the company-user instructions in Part B. Do not take over their finance or HR work.

## C8. Platform troubleshooting

| Problem | What to do |
|---|---|
| Cannot see the Platform admin menu | Ask another platform admin to add your e-mail; you must have signed in once. |
| A sign-up is blocked | Read the **Still blocking** line and the checks; ask the owner for the missing item. |
| Owner left the company | Use **Change the owner** on the workspace; the new owner must be an active user. |
| Company cannot sign in | Check the workspace status: **Suspended** and **Closed** block sign-in. |
| Wrong plan or trial | Open the workspace drawer and change plan or trial end date. |
| A document is too visible | Use **Restrict** on the file in the activation review. |

---

# Appendix 1 — The end-to-end workflow

```
Register → Verify → NDA → MSA → Project → SOW → Acceptance
        → Resource contract → Acceptance → Timesheet → Invoice → Payment → Confirmation
```

| Step | Who does it | Where |
|---|---|---|
| Register / verify | Individual or company owner | Create account / My companies |
| NDA | Legal / account manager, both companies | MSAs & SOWs → Add agreement (NDA) |
| MSA / subcontract | Legal / account manager | MSAs & SOWs → Add agreement |
| Project | Account manager | Projects & placements → New project |
| SOW / work order | Legal / account manager | MSAs & SOWs → Add SOW |
| Acceptance | Both companies | SOW page → Approve / e-signature |
| Resource contract | HR / account manager | Offer letter (W-2/1099) or vendor work order (C2C/E2E) |
| Acceptance | The resource / company | E-signature |
| Timesheet | Consultant submits; company and end client approve | My timesheet / Timesheets |
| Invoice | Finance (or automatic on final approval) | Invoices |
| Payment | Finance records; customer/vendor may record their side | Invoice / Payment flow / Partner portal |
| Confirmation | Finance or the payee | Invoice → Confirm / My work → Acknowledge payment |

# Appendix 2 — Status meanings

| Status | Meaning |
|---|---|
| Draft | Being prepared; not visible to the other company yet. |
| Pending | Sent; waiting for the other company's answer or signature. |
| Out for signature | In an e-signature envelope; not yet fully signed. |
| Active / Accepted | In force. |
| Expired | Past its end date; gates depending on it are blocked. |
| Rejected | Turned down; needs correction and resubmission. |
| Submitted | Timesheet sent for approval; locked. |
| Approved | Timesheet accepted; invoices can be generated. |
| Returned | Timesheet sent back for changes, with a reason. |
| Received | Vendor invoice recorded; three-way match pending. |
| Exception | Vendor invoice hours do not match approved timesheets. |
| Held | Pay-when-paid; waiting for the customer to pay. |
| Ready to pay / Scheduled | Released for payment. |
| Part paid | Some money recorded; balance remains. |
| Paid | Invoice settled. |
| Completed | Payment recorded but not yet confirmed. |
| Confirmed | Payment acknowledged by finance or the payee; lifecycle closed. |
| Void | Cancelled; no further payments. |

# Appendix 3 — Module map by audience

| Module | Individual user (no company) | Company user | Platform admin |
|---|---|---|---|
| Dashboard | — | Staff and client users; KPIs and suggestions | Platform-wide totals in the console |
| My work | — | Consultant: projects, chain, payment status, acknowledge | Counts only |
| My timesheet | — | Consultant: enter, save, submit per project | Counts only |
| Policies & documents | — | Consultant: accept policies, view agreements, sign | Activation documents only |
| Expenses & time off | — | Consultant submits; HR/finance/approver decides | — |
| Network | Feed, people, connections, messages | Same, plus company audience | Same as a person |
| My companies | Create, resume, join, open | Switch workspace | — |
| Profile / Account & security | Full | Full | Full |
| Clients & vendors | Own company profile | Add, edit, view agreements/SOWs/documents | Company list, plan, status, aggregate money |
| Consultants | — | Onboard, checklist, offboard, rehire | Counts only |
| Projects & placements | — | Create, edit, contract gates | Counts only |
| MSAs & SOWs | Sign offers/NDAs | Create, send, amend, approve, NDA gate | — |
| E-signatures | Sign only | Create, send, remind, void, download | — |
| Timesheets | Submit | Approve, return, bulk approve, history | Counts only |
| Invoices | — | AR/AP, payments, credit notes, reminders | Aggregate invoiced/collected/paid |
| Payment flow | Status in My work | Full chain for their company | Aggregate money |
| Payroll, 1099 & referrals | Expenses/time off | Finance/HR/approver tabs | — |
| Compliance | Accept policies | Documents, work auth, policies, registrations, reminders | Company docs during activation |
| Import & export | — | Finance/HR/legal | — |
| Audit log | — | Legal/finance | Platform admin actions are audited |
| Users & roles | — | Admin invites and edits users; owner manages roles | Change owner only |
| Company settings | — | Admin: company, sign-in, workflow, numbering | Plan, status, trial |
| Roles & permissions | — | Owner only | — |
| Partner portal | Vendor/client after invite | Vendor/client login | — |
| Platform admin | — | — | Full console |

---

*This guide is a companion to `docs/user-manual.md` (the full feature manual) and `docs/training-guide.md`
(hands-on sessions). When a screen changes, update this guide and the user manual together.*
