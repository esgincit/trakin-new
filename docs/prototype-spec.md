# myTrakIn — prototype specification (every screen, field, action and rule)

This is a complete written record of the requirement prototype
[`docs/prototype/mytrakin-prototype.html`](prototype/mytrakin-prototype.html) (copied from the customer's file
`mytrakin-prototype (1).html`, 441,898 bytes, received 2026-10-13). Open the HTML in a browser and use the
**Demo role** selector to see each screen.

- **What to build** → this file. **What is built / what is next** → [PLAN.md](PLAN.md) (requirement IDs and status).
- Section headings carry the PLAN.md ID prefix (e.g. `[AR]`) so every requirement can be traced back here.
- The prototype is a single file that was extended in layers: later code replaces earlier screens. Where an early
  version was replaced, this spec describes the **final** behaviour and notes the superseded one as *Superseded*.
- Names in the prototype: the tenant is **Executive Software Guild Inc. (ESG)**. In the product "ESG" = "the tenant"
  (any staffing company). "Today" in the demo is fixed to **2026-10-10**.

Contents: 1 Shell · 2 Roles & visibility · 3 Core money model & formulas · 4 Public pages · 5 Platform console ·
6 Tenant screens (in menu order) · 7 Consultant portal · 8 Profile & account · 9 Cross-cutting behaviour ·
10 Reference lists (checklists, templates, rules, statuses, constants) · 11 Demo data

---

## 1. App shell `[UX]`

**Left sidebar**: logo "mT myTrakIn"; menu grouped by section headers; a section header shows only if the role can
see at least one item in it. Items may show a **badge** (count):

| Item | Badge counts |
|---|---|
| My approvals | items in the approvals queue |
| My payments & documents (consultant) | consultant's pending to-dos |
| Registrations | registrations with status Pending |
| Consultant onboarding | not-active new hires starting in ≤14 days |
| Document expiry & emails | tracked documents expiring in ≤30 days |
| E-signatures | envelopes waiting for *my* signature |
| Sign-up approvals (platform) | sign-ups not Approved/Rejected |

Final menu order (sections → items):
- **Overview**: Dashboard · My approvals · Reports · My payments & documents
- **Onboarding**: Onboarding pipeline · Consultant onboarding · Registrations
- **Agreements**: MSA, SOW & agreements · E-signatures
- **Work**: Projects · Placements & chain · Timesheets
- **Payments**: Payment flow · Invoices & reminders · Client receipts (AR) · Vendor payouts (AP) (vendor sees label
  "My payments") · 1099 contractors · W-2 payroll · Referral payouts · Payment ledger
- **People & companies**: Consultants & work auth · Clients & vendors · Compliance · Document expiry & emails ·
  Network & messages
- **Administration**: Users & security · Approvals & hierarchy · Audit log · Data import & export
- **SaaS platform**: Platform dashboard · Tenant companies · Sign-up approvals · Plans & billing · Support & audit log
- **Account**: My profile & settings

**Header**: Menu button (phones) · workspace name ("myTrakIn Platform · owner console" for platform owner; vendor
company name for vendor; "<consultant> · ESG network" for consultant; tenant name otherwise) · **global search** box
"Search invoices, SOWs, people, projects…" (hidden for consultants) · *Demo role selector (prototype only)* · **AI
assist** button · **Alerts** button with count · *Public pages… (prototype only: Sign-in screen, Registration)* ·
**Theme** toggle · **avatar** (photo or initials) opening the account menu.

**Drawer** (right side panel) for record details and forms, closed by Close button or clicking the dim background.
**Toast** (bottom message, 2.6 s) after every action. **Overlay** (full screen) for public pages and the signer flow.

---

## 2. Roles & visibility `[ACC]`

Demo roles: Platform owner, Tenant admin (ESG), Finance (AR/AP), Account manager, Contracts/legal, Vendor admin
(BrightPath), Consultant (R. Kumar). Menu access per role: see PLAN.md §3.1 (final ACCESS lists). Switching role
keeps the current page if allowed, else opens the role's first page.

**Amount visibility on a payment hop** (`amtVis`):
- Upstream hop (a link the tenant is not party to) and W-2 payroll hop → never shown.
- Admin, finance → all tenant hops.
- Account manager → AR hops only.
- Vendor → only hops where the vendor is the payee.
- Everyone else → masked `••••`.

**SOW visibility** (`sowVis`): vendor → only SOWs with their company; AM → only "we bill" (supplier-side) SOWs;
others all. **SOW values** (`sowValVis`): finance/admin, legal, AM for supplier side, vendor for own SOWs.

**Rate on a chain link** (`rateVisible`): links where the tenant is neither buyer nor seller → never (rate is not even
stored). Finance, admin, legal → yes. AM → AR link only. Vendor → only the link where the vendor is the seller.

**Permission matrix** (shown as "Access matrix" tab): see PLAN.md §3.2. Footnote: "Scoped = assigned clients only
(account manager), own company's contracts and own link only (vendor), or a signing-authority dollar limit."

Other visibility rules:
- Company EIN visible to finance/admin; masked otherwise.
- Consultant work-authorization documents visible to HR, compliance and admins; others see status only.
- Payroll (salaries) visible to finance and company admins only ("W-2 payroll — Visible to finance and company admins
  only." for others).
- Vendors never see client amounts ("Billed to client" hours shown as `••••` to vendor in three-way match).
- Consultants never see any amounts or rates ("Rates and invoice amounts between companies are confidential and are
  not shown to consultants").

---

## 3. Core money model & formulas `[FLOW][AR][AP]`

**Billing cycle** = one placement × one period. Each cycle has **hops** (one per link in the chain):
- *upstream* hop (end client → prime): not tracked; shows "Client paid prime" if the prime reported a date, else
  "Awaiting client"; amount always masked; text "Not tracked · not our contract".
- *AR* hop: payer = customer, payee = tenant. Fields: invoice no, rate, hours, issued, due, terms, SOW, payments
  [date, amount, method, reference], collection notes.
- *AP* hop: payer = tenant, payee = vendor or 1099 contractor. Fields as AR plus `pwp` (pay-when-paid → AR invoice it
  waits for), `apprHrs` (approved hours when different), `exception` flag, `scheduled` run date.
- *payroll* hop (W-2): "ESG → W-2 payroll", "ADP payroll", no amount.

Formulas:
- invoiced = rate × hours; payable (AP) = rate × (approved hours if set, else hours); amount due = payable for AP,
  invoiced for AR; paid = sum of payments; balance = due − paid.
- daysLate = today − due, only when due < today and balance > 0.
- **Hop status** (in order): upstream → Client paid prime / Awaiting client; payroll → W-2 payroll; balance ≤ 0 →
  **Paid**; exception → **Exception**; pay-when-paid and the linked AR still has a balance → **Held**; pay-when-paid
  and AR paid → **Scheduled** if scheduled else **Ready to pay**; scheduled → **Scheduled**; part paid → **Overdue (part
  paid)** if past due else **Partially paid**; past due → **Overdue**; otherwise **Awaiting payment** (AR) / **Due** (AP).
- Status colours: good = Paid, Client paid prime; brand = Ready to pay, Scheduled, Awaiting payment, Due; violet =
  Partially paid; bad = Overdue, Overdue (part paid), Exception; warn = Held; muted = Awaiting client, W-2 payroll.
- **Cycle state**: any Overdue/Overdue (part paid)/Exception → **Action needed** (bad); all Paid → **Settled** (good);
  any Held → **Waiting on customer** (warn); else **In progress** (brand).
- **Expected payment date (AP)**: scheduled date; for pay-when-paid = linked AR due date + 3 days; else due date.
- **Margin** (finance only) = AR invoiced − AP payable; margin % = margin ÷ AR invoiced; cash position = AR paid − AP
  paid.
- **SOW stats**: invoiced = prior invoiced (before myTrakIn) + invoiced under this SOW; collected/paid = prior paid +
  payments; open = invoiced − collected; remaining = ceiling − invoiced; burn % = invoiced ÷ ceiling. Burn bar warn ≥75 %,
  bad ≥90 %.
- Days-left colour (`expTone`): <0 or ≤60 days bad; ≤120 warn; else good.
- Recording an AR payment releases every AP invoice whose `pwp` points at it (toast lists them: "… released for the
  next payment run").

---

## 4. Public pages

### 4.1 Sign-in `[AUTH]`
Step "choose": buttons
1. **Continue with single sign-on (SSO)** — Microsoft Entra ID, Okta, Google Workspace (SAML/OIDC)
2. **Email me a one-time code** — work email, or personal email for consultants and contractors
3. **Text me a code** — sign in with your mobile number
4. **Sign in with a passkey** — Face ID, Touch ID, Windows Hello or a security key

Note: "Admin, finance and approver accounts must also use a second factor (authenticator app or passkey). Passwords
are not used." Link "New here? Register a company, vendor or yourself".
- Step "id": email / work email / mobile field; Back; Continue (SSO) or Send code.
- Step "sso": "Redirecting to your identity provider — <email> belongs to a verified domain for <tenant>. You'll sign in
  with Microsoft Entra ID, which also enforces your company's MFA." Use another method / Continue.
- Step "otp": 6 boxes; "We sent a 6-digit code to <id>. It expires in 10 minutes." Resend code · Verify.
- Step "mfa" (roles that approve payments): "Code from your authenticator app" 6 boxes; "Use a passkey instead"; Sign in.
- Step "passkey": "Follow the prompt on your device"; Approve on device.
- Footer links: Privacy · Terms · Security. Every sign-in is audited ("Signed in · <method>").

### 4.2 Registration wizard `[REG]`
Stepper: **Who you are → Verify → Details → Documents → Review**, then Submitted.
- Step 0 types: **Staffing company** ("Start your own myTrakIn workspace — approved by myTrakIn") · **Vendor /
  supplier** ("Join ESG's network as a C2C vendor") · **Client** ("Work with ESG as a client company") · **Independent
  contractor (1099)** ("Self-employed; paid on your invoices") · **Consultant / employee** ("W-2 or C2C consultant
  joining a project"). Text: "Every registration is verified and approved before access is granted." Link "I already
  have an account".
- Step 1 Verify: Full name, Work email (business types) / Email (personal is fine), Mobile; Send verification code → 6
  boxes → Verify code → "✓ Verified". Businesses: "Free email domains (Gmail, Outlook) need extra verification and may
  be rejected." Cannot continue until verified ("Verify your email first").
- Step 2 Details — businesses: Legal company name (required), EIN, State of incorporation, Registered address; staffing
  company also Plan (Starter/Growth/Enterprise) and Expected users. Note: "We check the EIN against IRS records and
  the company status with the Secretary of State." Individuals: Legal name, Home state, Primary skills; "Your taxpayer
  ID is collected only on the secure W-9 form, never in free text."
- Step 3 Documents ("Upload what you have now; you can add the rest later. Files are virus-scanned and encrypted.")
  per type — see §10.6. Each row Needed/Uploaded + Choose file.
- Step 4 Review: type, name, email (Verified chip), documents n of N; checkboxes (all required, "Accept all terms to
  submit"): Terms of Service, Privacy Policy; consultants & 1099 also "I e-sign the Mutual NDA (view PDF)"; vendors also
  "I accept the Vendor Code of Conduct". Submit registration.
- Submitted: "<myTrakIn team | tenant> will verify your details and documents, usually within one business day. You'll
  get an email when your access is approved. Reference <R-xxx | G-xxx>."
- On submit: staffing company → platform **sign-up** (§5.5) with checks Email verified, Business domain (free-domain
  regex gmail|yahoo|outlook|hotmail|icloud|aol), Secretary of State active (state given), IRS EIN match (EIN given),
  OFAC screen; flag "Free email domain". Others → tenant **registration** (§6.4) with checks Email verified, Business
  email domain, IRS TIN match, OFAC; and a pipeline party at stage 1 "Awaiting verification".

---

## 5. SaaS platform console (platform owner) `[PLAT]`

### 5.1 Platform dashboard
Title "Platform dashboard — myTrakIn SaaS · tenant companies, onboarding progress and revenue · as of <date>".
KPIs: **Tenant companies** (n added this month) · **Live** (% of all) · **In onboarding** (n stalled · n not
activated; warn if any stalled) · **Monthly recurring revenue** (ARR = ×12) · **Avg time to go live** (days, created →
first payment) · **Revenue per user** (MRR ÷ paid seats; sub-text paid seats · payments tracked 30 d).
Cards:
- **Tenants added per month** (Apr–Oct): bars added vs went live, cumulative total.
- **Onboarding funnel** — "How many active tenants have reached each step" (8 steps, §10.2) + "Biggest drop: n tenants
  between '<step>' and '<step>'".
- **Onboarding in progress** table (not live, not suspended, sorted by step): company (+Trial chip), status, progress
  n/8, next step, last active ("Never"); link All tenants.
- **Revenue by plan**: plan · price/user, tenants, paying, MRR.
- **Recent platform activity** (last 4 audit entries).

Tenant status: **Suspended** if suspended; **Live** if step ≥ 8; **Invited** if step ≤ 2; **Stalled** if last
activity > 14 days ago; else **Onboarding**. Colours Live good, Onboarding brand, Invited violet, Stalled warn,
Suspended bad. MRR per tenant = 0 if suspended, trial or step < 3; else billed seats × seat price; billed seats =
max(users, plan minimum).

### 5.2 Tenant companies
"Every staffing company using myTrakIn. You create the tenant and invite its admin; the admin then manages the
company's own data." Search box, Export, **Add tenant company**. Status filter chips with counts: All, Live,
Onboarding, Invited, Stalled, Suspended. Table: Company (id · state), Plan (+Trial), Status, Onboarding bar n/8,
Admin, Users, Clients/vendors, SOWs, Payments (30 d), MRR, Created, Last active. Row → tenant detail.

**Tenant detail** drawer: name, status, plan(+trial), id; suspended banner "Suspended: <reason>. Users can sign in
read-only."; Tenant admin, State, Created (· live date, n days), Subscription ($/month, or "Trial — converts on
<created+14d>"), Last active ("Admin has not signed in"); usage tiles Users, Clients & vendors, SOWs tracked, Payments
tracked (30 d); **Onboarding checklist n/8** (done/next/to-do); actions: **Resend admin invite** (step < 3), **Send
check-in** (Stalled), *Mark next step done (demo)*, **Request support access**, **Suspend / Reactivate**. Footer:
"Platform staff cannot see a tenant's payment or contract data unless the tenant admin approves time-boxed support
access. Every access is logged."
- Request support access → audit "Requested 30-min support access to <tenant> — awaiting tenant admin approval"; toast
  "Request sent to <admin> for approval". Example approved entry: "Support access to Vantage IT Solutions for 30 min —
  reason: invoice import help (approved by tenant admin)".
- Suspend → reason "Suspended by platform owner", audited; Reactivate audited.

**Add tenant company** form: "Creates an isolated workspace and emails the admin an invite. The admin completes the
company profile and adds their own clients and vendors." Company legal name*, EIN, State of incorporation, Admin full
name*, Admin email*, Plan (Starter/Growth/Enterprise), **Start as 14-day trial** checkbox, **Modules** checkboxes:
Payments, MSA & SOW, Timesheets, Vendor portal, Community. Create and send invite → tenant at step 2, audited, toast
"Tenant T-0xx created — invite emailed to <email>". Validation: "Company name, admin name and admin email are required".

### 5.3 Plans & billing
"myTrakIn is priced per user per month, with a minimum seat count per plan. External users (vendor admins,
consultants, contractors) are free."
KPIs: MRR (ARR), Paid seats (n paying tenants), Revenue per user (ARPU per seat per month), Revenue per tenant (avg).
Plan cards:

| Plan | Price | Minimum | Includes |
|---|---|---|---|
| Starter | $29 /user/month | 3 users | Payments, MSA & SOW tracking, timesheets, 1099 and referral payouts |
| Growth | $49 /user/month | 5 users | Everything in Starter + vendor portal, onboarding & e-signature, reminders, accounting sync, network |
| Enterprise | $79 /user/month | 15 users | Everything in Growth + SSO / SCIM, VMS and payroll integrations, custom approval chains, dedicated support |

Each card: n tenants · MRR. Table "October 2026 subscription invoices": Tenant, Plan, Users, Billed seats, Price,
Amount, Status (Paid / Due Oct 15 / Overdue 60+ days). Only non-trial tenants at step ≥ 3.
*Superseded*: an earlier version had flat plans Starter $299/mo (up to 25 placements, 5 users, payments, MSA & SOW),
Growth $799/mo (150 placements, 25 users, vendor portal, timesheets, accounting sync), Enterprise custom (unlimited,
SSO/SCIM, VMS integrations, dedicated support).

### 5.4 Support & audit log
"Every platform-level action and every support access to tenant data." Table Date, By, Action. Footer: "Platform staff
have no default access to tenant data; access is requested, approved by the tenant admin, time-boxed and recorded here."
Example actions: created tenant & invited admin; support access granted; created trial tenant; "Suspended Old Mill
Contractors — subscription unpaid 60+ days; data retained read-only"; approved/rejected sign-up; requested info.

### 5.5 Sign-up approvals
"Staffing companies that registered for their own workspace. Verify the business before creating the tenant."
Preview public sign-up. One card per sign-up: company, status (Pending, Needs info, Approved, Rejected), id · plan · n
users · submitted date; **Flag** banner (e.g. "Free email domain and no proof of incorporation"); contact · email,
state, EIN; **Verification** chips ✓/✕: Email verified, Business domain, Secretary of State: active, IRS EIN match, OFAC
screen; **Company documents** chips: Certificate of incorporation, EIN letter (CP 575 / 147C), Signatory photo ID.
Actions (Pending/Needs info): **Request info** (status → Needs info, e-mail sent), **Reject**, **Approve & create
tenant** (or **Approve anyway** if a check/document is missing) → tenant created at step 2, admin invited, audited,
toast "workspace created and admin invited".

---

## 6. Tenant screens

### 6.1 Dashboard `[DASH]`
Title "Payments dashboard — <tenant> · as of <date>".
KPIs (6): **Receivable outstanding** (n open client invoices) · **Overdue from clients** (n invoice, oldest n days
late; bad) · **Collected (30 days)** (n receipts) · **Payable to vendors** (n open vendor invoices; `••••` "Finance
only" for non-finance) · **Held vendor payments** (pay-when-paid or exceptions; warn; finance only) · **MSA / SOW
expiring** (SOWs ending in 0–60 days + MSAs ≤ 90 days).
Cards:
- **Smart suggestions** (AI, top 4, "See all & ask") — not for vendor/consultant. See §9.4.
- **Expected cash in vs out — next 6 weeks**: rows Past due + 6 weeks; bars "Expected from clients" (AR balances by due
  date) and "Due to vendors" (finance only; AP balances by expected payment date, exceptions excluded). Note: "Vendor
  dates use the scheduled run, or for pay-when-paid the client invoice due date + 3 days. Exceptions are excluded until
  resolved."
- **Needs attention**: Overdue (AR, "n open · n days late"), Exception (finance; "Invoiced n hrs, approved n hrs"),
  Held (finance; "Pay-when-paid on <AR>"), Ceiling (visible SOWs ≥90 % burn; amendment status or "No amendment
  raised"), MSA (expiring ≤90 days; renewal note). Each opens its record. Empty: "Nothing needs attention."
- **Missing & expiring · n** — "Agreements, documents, policies, work authorization, timesheets"; top 8 rows (type chip,
  who, what, Open ›); "Open checklist". Engine §9.3.
- **Open payment flows** (top 4 not settled) + View all.

**Vendor dashboard** ("Payments from ESG — <vendor> · as of"): KPIs Invoiced to ESG (n invoices), Paid by ESG (last 60
days), Waiting on client (pay-when-paid, warn), Next expected payment (estimated); table "Your invoices".

### 6.2 My approvals `[APR]`
"Items waiting for a decision, routed by the approval chains in Approvals & hierarchy." Table: Type (chip), Reference,
Detail, Requested by, Current step, Amount, **Reject** / **Approve**. Empty "Nothing waiting for you." Footer:
"Bank-detail changes need a second approver plus a phone callback to a contact already on file. Every decision is
written to the audit log."
Item types and demo examples: Vendor invoice exception ("BrightPath billed 72 hrs; 64 approved. Accept at 64 hrs?",
step "Finance manager (≤ $25,000)", $5,248) · SOW amendment ("Extend Supplier Portal BTP SOW to Feb 26, 2027 and add
$36,000", "Legal review") · Payment run ("4 payees, ACH", "Company admin (dual approval > $25,000)", $27,552) · Bank
detail change ("Account ••••4410 → ••••9921. Callback to known contact required.", "Finance manager + phone callback") ·
Rate change ("Vendor rate $99 → $101/hr from Nov 1 (margin 15.8%)", "Finance manager") · Registration ("New C2C vendor;
COI and bank verification outstanding", "Compliance → Company admin") · Timesheet ("40 hrs Supplier Portal", "ESG
delivery manager") · Expense ("Mileage $58.30 · billable to Atlas Foods", "ESG admin") · Time off ("Unpaid leave ·
client approver to be notified", "ESG admin").
Approve effects: exception → hours set to approved, exception cleared; registration → registration approved;
timesheet → timesheet approved & locked; expense → Approved/Rejected; time off → Approved/Declined. All audited; nav
badge updates.

### 6.3 Reports `[RPT]`
"Standard reports for finance, operations and compliance. Each opens the live data with search, filters and CSV
export." Filters: period (This month, Last month, Quarter to date, Year to date, Custom range…), customer (All /
each). **Schedule monthly pack**. Report cards (only those whose screen the role can open), each with **Open** and
**Export CSV**:
AR aging (open client invoices by age bucket and customer) · AP aging & payment run (vendor and 1099 payables, held
items and run proposals) · Cash forecast (expected receipts vs payments by week) · Margin by placement (AR minus AP for
every billing period) · Timesheet compliance (submitted, approved and missing by week) · Hours by consultant & project
(every approved week) · SOW burn & expiry · MSA & agreement expiry (incl. NDAs and missing items) · 1099 summary
(payments and 1099-NEC readiness) · Payroll register (W-2 gross, employer taxes and margin) · Referral fees (accrued,
paid and blocked) · Work authorization (expiry dates and I-9 reverification due) · Onboarding status (companies and
consultants by step) · Audit trail (data changes, sign-ins and approvals).

### 6.4 Onboarding pipeline & registrations `[ONB]`
**Pipeline**: "Every client, vendor, 1099 contractor and consultant moves through the same steps before money can
flow: register → verify → agreement → SOW → e-signature → project → timesheets → invoicing." KPIs: In onboarding
(stage < 8, "Not yet invoicing"), Fully live ("Timesheets and invoices flowing"), Blocked (stage < 8 with a blocker,
"Waiting on a document or signature"; warn), Awaiting approval (pending registrations). Buttons **Open public
registration**, **Invite company or person**. Table: Party, Type, 8 stage columns (✓ done / "Next" / ·), Blocker.
Stages §10.2. Row → party detail: checklist n/8, blocker banner, **Send reminder**, (*demo: mark next step done*),
"Fully onboarded."
**Invite to onboard** form: "Sends a secure link. They verify their email, add details and documents, then you
approve." Type (Client, Prime vendor, C2C vendor, 1099 contractor, W-2 consultant, C2C consultant), Company or person
name*, Email*, Mobile (optional, for SMS reminders). → party "Invite sent — waiting for registration", e-mail logged,
audited.

**Registrations**: "Outside companies and people who registered through the public page. Nothing is accessible until
verification passes and you approve." Preview public registration. Card per registration: name, type, status (Pending
/ Approved / Rejected), id · submitted; contact · email, state, EIN/TIN; **Verification checks** chips (Email
verified, Business email domain, IRS TIN match, Secretary of State: active, OFAC sanctions screen, Bank account
verified); **Documents** chips (✓ / Missing). Actions: Request info (e-mail "asking <contact> for the missing items"),
Reject, Approve (or "Approve anyway").
Approve: creates company (not for 1099/consultant) with status "Approved — agreement next"; pipeline party → stage ≥2
with next step: clients & vendors "MSA", 1099 "Independent contractor agreement", consultant "Offer letter / NDA";
removes matching approval item; "welcome email sent".

### 6.5 Consultant onboarding `[CON]`
"Onboard W-2 full-time employees, W-2 contract employees, C2C consultants and 1099 contractors. Each type has its own
checklist; a consultant can be assigned to any number of projects."
KPIs: In onboarding ("Not yet active") · Starting in 14 days ("Check I-9 timing", warn) · Ready to activate (only the
last item — project access — open) · Activated ("Moved to Consultants"). **Onboard consultant** (admin/legal/AM). Type
filter chips with counts. Table: Consultant (title), Type, Employer, Projects (count · names), Start (days), Progress
bar n/N, Next step (or Activate), Status (Onboarding / Ready / Active).
**Detail**: title, employer, email, start date (days), location; **Projects (n)** table: project, hours/week, AR bill
rate, AP rate or pay rate (rates for finance/admin only; W-2 full-time "Salary"; internal project "Internal");
"Total n h/week. There is no limit on how many projects a consultant can work on."; **Add another project** (project,
hours/week, AR bill rate, AP/pay rate); **Checklist** n/N with Mark done per item; W-2 note "Form I-9 and E-Verify only
after the offer is accepted; Section 2 is due within 3 business days of the start date."; files; **Resend onboarding
packet**; **Activate consultant** (disabled "Finish the checklist first" until all but the last item done).
**Activate**: marks all done; creates consultant record (W-2 / C2C / 1099) with defaults; creates one placement per
project (except internal) with AR link (customer = prime if via prime, rate = bill, doc "SOW pending", Net 30) and AP
link for non-W-2 (payee = vendor or "<name> (1099)", Net 15 for 1099 / Net 30), status Onboarding; adds to project
team; creates this week's empty timesheet; toast "<name> is active — sign-in invite and timesheet access sent".
**Onboard consultant** form: Engagement type (4), Employer (vendor, C2C only), Full name*, Email* (personal is fine),
Mobile, Job title, Start date (default today+14), Work location, **Projects** rows (project, h/wk, Bill $/hr, Pay $/hr;
Add another / Remove). "Assign as many projects as needed. Hours, AR bill rate and AP / pay rate are set per project."
→ "Create and send onboarding packet". Checklists per type: §10.1.

### 6.6 MSA, SOW & agreements `[AGR]`
"Client and vendor MSAs, 1099 contractor agreements, SOWs, offer letters, NDAs and policy acceptance — with value,
burn, signatures and expiry tracked." (Consultant role opening it is redirected to My payments & documents.)
KPIs: Active MSAs (n expiring ≤90 d) · Active SOWs (n ending ≤60 d) · SOWs over 90 % burn ("Amendment needed", warn) ·
Supplier-side value remaining (ceiling − invoiced; masked for vendor).
Toolbar (admin/legal/finance): "Already signed elsewhere?" **Add existing MSA** · **Add existing SOW** · Import MSAs ·
Import SOWs · SOW template · MSA template.
Tabs: **SOWs & work orders** · **MSAs & contractor agreements** · (admin/legal/AM) **Offer letters & NDAs** · **Policy
acceptance** · **Missing checklist (n)** · (not vendor) **Access matrix**.
- **SOW tab**: side filter All / We bill (client / prime SOWs) / We pay (vendor SOWs); **New SOW** (admin/legal/AM).
  Columns SOW/WO (We bill|We pay · MSA), Counterparty, Consultant, End (n days), Value, Invoiced, Collected / paid,
  Remaining, Burn bar, Status (amendment status chip, or Ending soon if ≤60 days, else Active). Footnote: "Collected /
  paid = cash received from the client for 'we bill' SOWs, and cash paid to the vendor for 'we pay' SOWs."
- **MSA tab**: MSA (kind), Counterparty, ESG is (Supplier/Buyer), Effective, Expires (days chip), Payment terms,
  Renewal, Notice, SOWs, SOW value. Kinds: MSA, Independent contractor agreement (1099), Subcontractor agreement, NDA.
- **SOW detail**: side chip, amendment chip; Title, Under MSA, Term (days left), Consultant; **Flows down from**
  <client SOW> (ends …); **Flows down to** <vendor SOWs>; value block (ceiling, remaining, invoiced, burn bar,
  collected/paid to vendor, open) or "Values are hidden for your role."; Amendment (id, text, status); warnings "This
  SOW runs past the upstream SOW it supports." and "A downstream vendor SOW ends before this one — extend it before the
  consultant's term runs out."; invoices under the SOW (invoice, period, amount, status); actions Draft amendment, Send
  for signature (admin/legal), View signed copy; **Files** (signed copy); **E-signatures** section (envelopes for the
  SOW and its amendment with signer progress and IPs, or "No e-signature envelope. If it was signed on paper, upload
  the signed copy below.") + Send for signature.
- **MSA detail**: supplier/buyer chip, days left; counterparty, effective → expiry, payment terms, renewal, notice,
  insurance required, signed by; SOWs under it (SOW, consultant, ends, burn); warning when expiring ≤ 90 days "Expires
  in n days, before some/none of its SOWs end. New SOWs and payments under it will be blocked after expiry."; Start
  renewal (admin/legal); View signed copy; files; e-signatures.
- **Offer letters & NDAs**: "Send agreement for e-signature"; per consultant: Type, Offer letter (W-2), Contractor
  agreement (1099), NDA (Signed <date> / status), Policies n/N accepted. Note: "C2C consultants' employment paperwork
  (offer, I-9) sits with their employer; ESG still collects an NDA and policy acceptance directly."
- **Policy acceptance**: Manage policy library · Request acceptance; matrix consultant × policy: Not required /
  Accepted <date> / Pending. "Acceptance is recorded with timestamp, policy version, IP and device. A new version
  re-opens acceptance for everyone it applies to."
- **Missing checklist**: "Every client and vendor needs an MSA; every 1099 contractor an independent contractor
  agreement; every W-2 consultant an offer letter; every consultant an NDA and the required policies." rows with
  **Remind**.
- **Add existing MSA or agreement**: "For agreements already signed outside myTrakIn. Upload the signed copy so it's on
  file." Agreement ID*, Type (MSA, Subcontractor agreement, Independent contractor agreement (1099), Mutual NDA),
  Counterparty (companies + 1099 contractors), ESG is (Supplier — we bill them / Buyer — we pay them), Effective*,
  Expiry*, Payment terms (Net 30, Net 45, Net 60, Pay-when-paid, Net 15), Renewal, Notice period, Insurance required,
  Signed by (ESG), Signed copy (PDF). Duplicate ID → "already exists — open it to update".
- **Add existing SOW or work order**: "It must sit under an MSA — add the MSA first if it's not here." SOW/WO ID*,
  Under MSA, Side (We bill / We pay), Title, Consultant(s), Project, Start*, End*, Value / ceiling, Already invoiced to
  date, Already collected / paid to date, Flows down from (client SOW, for vendor SOWs), Signed copy. Adds the SOW to
  the project's SOW list (we-bill side).
- *Superseded* send form (replaced by §6.7): Agreement (Mutual NDA, Offer letter, ICA, MSA — client, MSA — vendor,
  SOW/work order, Policy acknowledgement), Send to, **Template version** (Current approved template / Custom — requires
  legal approval), **Countersigner** (Madhavi Gonnala / N. Patel ≤ $250k). Keep template-version and countersigner
  (with signing limit) as requirements.

### 6.7 E-signatures `[ESG]`
"Send MSAs, SOWs, amendments, NDAs, offer letters and contractor agreements to clients, vendors and consultants for
legally binding electronic signature. Every view and signature records the time, IP address, device and location."
KPIs: Needs your signature (vendor: "Sign as <vendor>", tenant: "ESG countersignature") · Waiting on others
("Reminders every 3 days") · Completed ("Sealed with a certificate") · Average time to sign (days, sent → completed).
**Send document for signature** (admin, legal, AM, finance). Tabs with counts: Action required · Waiting · Completed ·
Drafts · All. Table: Envelope (id, ref), Document, Signers (A → B), Progress (n of N signed), Sent, Last activity,
Status, **Sign now** when it's my turn. Footer: ESIGN Act / UETA; e-mail code + consent; sealed SHA-256, "any later
change is detectable".
- Envelope status: Voided; Draft (not sent); Declined (any signer declined); Completed (all signed); Expired (past
  expiry); else "Waiting for <current signer>". Signer statuses: Waiting, Sent, Viewed, Signed, Declined.
- Visibility: vendor → envelopes with a signer from their company; consultant → envelopes they sign. "Mine" = I am the
  current signer (tenant admins/legal sign for the tenant).
- **Envelope detail**: title, status, id · ref · sent by · expires; signers in order with status chip, signature image,
  timeline rows: Sent (email to …), Viewed (IP, device), Consented to electronic records (ESIGN / UETA disclosure),
  Signed (IP, device, location, verified by), Declined (time, reason), or "Not sent yet — receives the document after
  the previous signer"; **Sealed** <date> SHA-256 <hash>. Actions: Send for signature (draft), Remind <signer>, Sign
  now / Open signing link, Certificate of completion, Download signed PDF, Void.
- **Certificate of completion**: "tamper-evident record attached to the signed PDF"; document, reference, sent by,
  sent, completed, SHA-256, legal framework (U.S. ESIGN Act and UETA); per signer: signature, events table
  (Sent/Viewed/Consented/Signed × time, IP, device), identity method, location, signature type. Download certificate
  (PDF).
- **Send form**: Document (any MSA/agreement, SOW, amendment, templates **Mutual NDA**, **Offer letter — W-2**,
  **Independent contractor agreement — 1099**, or **Upload another document (PDF)…**), PDF upload (when Upload),
  Envelope title (pre-filled), Signers (name, email, company; counterparty contact pre-filled first, tenant signatory
  second; Add signer / Remove), **Sign in this order**, Expires after (days, default 30), Remind every (days, default 3),
  Message ("Please review and sign. Contact N. Patel with any questions."). Note: "Signers verify their email with a
  one-time code. We record time, IP address, device and approximate location for every view and signature."
  Validation: title; every signer name + valid email. Save draft / Send.
- **Signer experience** (from e-mail link, overlay "Secured by myTrakIn · <envelope>"): step 0 "<sender> sent you a
  document to sign — To protect this document we emailed a 6-digit code to <email>" (Resend code) → **Verify and open
  document** (records viewed time, IP, device) → step 1 Review document (rendered document text + signature blocks) +
  checkbox "I agree to use electronic records and signatures. I have read the ESIGN / UETA disclosure and can ask for a
  paper copy." → Continue (consent time) or **Decline to sign** (reason, shared with sender; sender e-mailed) → step 2
  Adopt signature: Full legal name, Type / Draw (canvas, Clear), checkbox "I understand this is a legal representation
  of my signature.", notice "When you sign we record the time, your IP address, your device and approximate location."
  → Sign document → step 3 Signed: "Thank you … We've sent it to <next> to sign next" or "Everyone has signed — the
  completed document and certificate have been emailed to all parties."; signed at / IP / device / verified by;
  Download a copy; Done.
- On sign: next signer becomes Sent and is e-mailed; when last signs: completed, SHA-256 seal, everyone e-mailed
  ("Completed: <title> (signed PDF + certificate)"), **completion actions**: amendment → status Signed (applied); MSA
  renewal → expiry extended, compliance doc valid, expiry tracker updated; NDA → consultant NDA Signed today.
- Remind → e-mail log + audit; Void → signers notified; all steps audited (viewed, signed, declined with IP/device).

### 6.8 Projects `[PRJ]`
"Each project ties a client, its SOWs, the team and their timesheets together." **New project** (admin/AM).
Cards (or list): name, status (Active / Internal), id; client (via prime); dates; description; team avatars; "$x of $y
invoiced" (finance). List columns: Project, Client, Status, Start, End, Team, People, SOWs, Invoiced (finance).
Detail: client (via), dates, ESG manager, client approver, description, **Team** (name, role, engagement, allocation),
**SOWs** (SOW, ends, burn) or "Internal project — no client SOW.", **This week's timesheets** (status per member),
**Files** (editable except vendor/consultant).
New project form: Project name*, Client (clients and primes), Linked SOW(s) (multi, supplier side), Description,
Client timesheet approver, Start, End.

### 6.9 Placements & chain `[PRJ-03]`
"ESG tracks only its own two links: the bill rate to its customer (AR) and the pay rate to its vendor or contractor
(AP). Rates between other parties are never stored." Vendor sees only placements where it is a seller.
Card per placement: person, type chip (C2C / W-2 / 1099), status (Active, Ending soon, Onboarding, Completed, Ended),
role · project · id, **chain diagram**: [End client — `••••` "Not our contract · Not tracked"] → Customer (prime) →
**AR** rate/hr · doc · terms → **Us** → **AP** rate/hr · doc · terms → Vendor / 1099 contractor → type → Consultant;
W-2: → "W-2 Payroll" → Employee.

### 6.10 Timesheets (approver view) `[TS]`
"One timesheet per consultant per week. The admin validates each one against the automatic checks and approves it;
approved hours feed the client invoice (AR) and the vendor or contractor payable (AP)."
KPIs: Waiting for approval · Approved ("Locked — feeding AR and AP") · Not submitted ("Reminders running") · Flagged by
checks ("Review before approving"). Week tabs (Week of Sep 27 – Oct 3, Week of Oct 4 – 10, **All weeks (history)**).
Admin: "Click a row to review hours and checks." / others "View only — the company admin approves timesheets."
Buttons: **Approve n that pass all checks**, **Remind n not submitted**. Table: Consultant, Type (· vendor), Project(s),
Sun…Sat (day >12 h red), Total, Checks summary (n failed / n to review / All checks pass), Status (Approved, Submitted,
Not submitted, Rejected), row action Approve / Remind. Footer: "Reminders go out Friday 3:00 PM and Monday 9:00 AM until
a timesheet is submitted. Approved timesheets lock; corrections need an adjustment that the admin approves again."
Below: "Week of … — all consultants · n not submitted · **Send reminders now**" table (consultant, project, status,
reminders "Sent Fri 3:00 PM · next Mon 9:00 AM · escalate Tue"), "Rules are set in Invoices & reminders → Reminder rules."
**Validation checks** (pass / review / fail): Submitted by consultant · No day over 12 hours (highest day) · Within
weekly allocation (logged vs allocated; review) · No weekend hours (review: "confirm the client asked for it") · W-2
only: overtime > 40 h at 1.5× pay (review) · Fits remaining SOW value per project (needed vs left; amounts for
finance/admin else "Checked"; fail) · Placement active for the whole week.
**Detail**: grid per project (internal "Internal · non-billable"), totals, consultant note, rejection reason, checks
list, **What approval creates** (finance/admin): AR — bill to <customer> $x; AP — pay <vendor/contractor> $y, or "W-2
payroll (no vendor payable)"; "Approved by … on …. Locked."; Submitted → Reason (required to reject: "Enter a reason
so the consultant knows what to fix"), **Reject**, **Approve** / **Approve after review**; Approved → **Request
adjustment**.
**History (all weeks)**: KPIs Timesheet lines ("One per consultant, week and project"), Approved hours, Consultants,
Projects (incl. completed); table Consultant, Week, Project, Hours, Status, Approved by, Billing (Invoiced and paid /
Invoiced <month> / In next invoice / Internal — not billed).
*Superseded*: first version had a 5-step chain Consultant → Vendor admin confirms → ESG delivery reviews → Client
approver approves → Locked. Final rule: consultant submits → tenant admin validates and approves → locked.

### 6.11 Payment flow `[FLOW]`
"Each row is one billing period for one placement: what ESG bills its customer (AR) and what ESG pays its vendor or
contractor (AP). Other layers in the chain are not tracked." Filter chips with counts: Open (default), Needs action,
Settled, All. Legend: Paid, Awaiting/scheduled, Part paid, Held (pay-when-paid), Overdue/exception.
Row: person, period · placement · hours, client, hop cards (who "AR · Northwind → ESG", amount or `••••`, status ·
date: "paid <date>" / "after client pays" / "due <date>"), cycle state chip, Margin (finance).
**Detail**: hop cards; finance block: Billed to <customer> $ / received, Owed to <payee> $ / paid, "Margin on this
period: $x (n%). Cash position today: $y."; **Timeline** sorted by date: invoice issued (hours · amount or "amount
hidden" · terms), each payment (method · ref), became overdue (n days late), held (released when <AR> is paid), failed
three-way match (invoiced vs approved); actions **Record client payment**, **Open vendor invoice** (finance).

### 6.12 Invoices & reminders `[AR]`
"Create client invoices from approved time, and let reminders and follow-ups run automatically." **Create invoice**
(finance/admin). Tabs: **Follow-up queue** (default) · **Reminder rules** · **Reminders sent** · **All client invoices**.
- Follow-up queue: open AR sorted by next reminder: Invoice, Customer, Balance, Due (n days late), Next automatic
  reminder (date · "courtesy notice" or "overdue notice (+ escalation ≥15 days)"), Owner ("Auto" or "K. Reddy
  (finance)" when ≥15 days late), **Send now**. Next reminder: if late → due + first of [1, 7, 15, 30, 45, 60] greater
  than days late (else today + 7); if not late → due − 7 if still ahead, else due date.
- Reminder rules: Area, Rule, Channel, On toggle (list §10.4).
- Reminders sent: When (date, time), To, Reminder, Channel.
- All client invoices: Invoice, Customer, Consultant · period, Amount, Due, Status.
**Create client invoice** form: "Pulls the contracted rate from the SOW and payment terms from the MSA. Hours default
to approved timesheets." SOW / work order (supplier SOWs: id · customer · consultant), Billing period (Oct 1–15, 2026 /
Oct 2026 / Sep 2026), Approved hours ("Enter approved hours"), Rate (from SOW, read-only, "$95/hr · Ravi Kumar"), Bill
to · terms · due date (read-only, due = today + terms days), PO / memo, **Invoice total** live, "Automatic reminders 7
days before, due date, +1, +7, +15 days". Save draft / **Create and send** → new AR invoice number
(ESG-AR-YYYY-NNNN), upstream hop added when billed to a prime, e-mail logged "Invoice … sent", audited ("<SOW> · n hrs ×
$rate = $total"), opens Client receipts.

### 6.13 Client receipts (AR) `[AR]`
"Money owed to ESG by clients and prime vendors. Recording a payment releases any pay-when-paid vendor invoice tied to
it." Cards: **Receivable aging** bars Current, 1–30, 31–60, 61–90, 90+ (by days late, open balances); **By customer**
(Customer, Open, Overdue, Terms) + "Open credit: $840 for Atlas Foods (ESG-CN-2026-0007)". Tabs: Open (default),
Overdue, Paid, All, **Credit notes**.
Table: Invoice, Customer, Consultant/period, SOW/PO, Amount, Received, Balance, Due (n days late), Status, **Record
payment** (finance). Credit-notes tab: Credit note, Customer, Against, Date, Reason, Amount (negative), Status ("Open —
apply to next payment"). Demo: ESG-CN-2026-0007 to Atlas Foods against ESG-AR-2026-0391, $840, "8 holiday hours billed
at regular rate".
**Invoice detail**: Bill to, Consultant · period · hours × rate, SOW/PO, Issued/due (terms); upstream status (if via
prime); **Linked vendor bill** <AP inv> (payee) — status; Invoiced, Balance; Payments received (date, method, reference,
amount); **Collection notes** (date chip, text, by) + add note (finance); **Record payment**, **Send reminder**,
**Download PDF**.
**Record payment** form: "<inv> · <customer> · balance $x"; Amount received (capped at balance; "Enter an amount"),
Date received (default today), Method (ACH, Wire, Check, Virtual card), Reference / remittance number (default "Manual
entry"). Audited "Recorded payment — $x received · balance $a → $b".

### 6.14 Vendor payouts (AP) `[AP]`
"Money ESG owes sub-vendors. Nothing is paid until hours match approved timesheets and, for pay-when-paid, the client
has paid." Tabs: **Payment run** (default) · **All vendor invoices** · **By vendor**.
- Payment run: KPIs Ready for this run (Ready to pay/Due/Scheduled balances, "Matched and eligible"), Held: pay-when-paid
  ("Waiting on client receipt", warn), Held: exceptions ("Hours or rate mismatch", bad). Table with checkboxes (only
  Ready to pay / Due / Scheduled selectable): Vendor invoice, Vendor, Consultant/period, Invoiced, Payable, Paid, Terms,
  Expected, Status. Footer: running total "n selected · $x", method select **ACH (NACHA file)** / Wire / Check,
  **Preview remittance**, **Approve and pay selected** ("Select at least one eligible invoice") → payments recorded
  (reference ESG-ACH-nnnn), toast "Paid n invoice(s), $x — remittance emailed to vendors", audited.
- All vendor invoices: same table without checkboxes.
- By vendor: Vendor, Invoiced, Paid, Open, Of which held, MSA chips (id · expiry, coloured), Compliance chips (non-valid
  docs e.g. "Certificate of insurance: Due soon", "W-9: Missing") or OK; "Totals cover invoices in this demo period";
  **Imported payment history (before myTrakIn)**: Vendor, Invoice, Period, Consultant, Amount, Paid, Reference + Sample
  template + **Upload old vendor payments**.
- **Vendor invoice detail**: Vendor, Consultant · period, Vendor SOW, Terms (— tied to client invoice), Issued,
  Expected payment; **Three-way match**: Vendor invoice n hrs | Approved timesheets n hrs | Billed to client n hrs
  (masked for vendor); chip "Mismatch: n hrs over approved time" or "Hours and rate match"; Payable, Paid; payments;
  actions (finance): **Return to vendor**, **Accept at n approved hrs** (exception); **Schedule for <next run>**
  (ready/due). Accept → "corrected to n hrs ($x) and now eligible".
- **Vendor role "My payments"**: "Invoices <vendor> has sent to ESG and when each will be paid." table; "Pay-when-paid
  invoices are released automatically when ESG receives the matching client payment. Client amounts are not shown to
  vendors."

### 6.15 1099 contractors `[PAY]`
"Self-employed individuals paid on their invoices, plus individuals paid referral fees. ESG issues 1099-NEC forms at
year end." KPIs: Active 1099 contractors (plus referral partners), Paid in <year> (all 1099 payees), Due in next run,
1099-NEC forms to file ("Due to recipients and IRS by Jan 31, <year+1>").
Table: Payee (role), Agreement, W-9 / TIN chip (On file · IRS TIN matched / Missing — 24% backup withholding if paid /
Not received), Terms ("$65/hr · Net 15 · ACH"), Paid <year>, 1099-NEC (Will be issued if ≥ threshold / Below
threshold). Note: "Reporting threshold is set to $2,000 for 2026 payments (configurable in settings; confirm with your
tax advisor). Payments to a payee without a valid W-9 are held, or backup withholding is applied." Then **Contractor
invoices** table (same as AP) + "Contractor invoices go through the same three-way match and payment run as vendor
invoices. <name> is not on payroll: no tax withholding and no benefits."

### 6.16 W-2 payroll `[PAY]`
"Semi-monthly payroll for ESG's W-2 contract employees. Processed in ADP; myTrakIn imports the register to track
employee cost against billing." KPIs: Employees on this run (billable and bench), Gross pay (period), Total employer
cost (gross + employer taxes + benefits), Paid on / Pay date (status). Run tabs (e.g. "Sep 16–30 · Paid", "Oct 1–15 ·
Scheduled").
Table: Employee (+ "Incl. $1,000 referral bonus (supplemental)"), Basis (Hourly $/hr or Salary $/yr), Hours (88),
Gross, Employer taxes (est.), Benefits, Total cost, Net pay (est.); Total row. Scheduled run: "Hours lock when
timesheets are approved on <date>. **Send approved hours to ADP**". **Margin on W-2 employees (per hour)**: Employee,
Bill rate, Loaded cost (= (gross × 1.0865 + benefits) ÷ 88), Margin $ (%), Note (Billable / "Bench — $x per pay period
with no billing"). Footer: "Employer taxes estimated at 8.65% (FICA 7.65% plus unemployment); the payroll provider's
register is the source of truth. Salary data is visible to finance and company admins only." (Prototype estimates:
hourly gross = rate × 88; salary gross = salary ÷ 24; net ≈ 74 % of gross.)

### 6.17 Referral payouts `[PAY]`
"Fees owed to people and vendors who referred a consultant. Accruals follow billed hours or a waiting period." KPIs:
Active referral agreements (people, vendors and employees), Accrued to date, Paid (all time), Payable now ("Included in
next run once approved"). **Add referral agreement**.
Table: Referrer (type), Referred consultant, Terms, Basis to date (billed hours), Accrued, Paid, Open, Status, **Pay**
(finance, when open > 0). Accrual: hourly = min(billed hours of consultant, cap) × rate; one-time = amount once today ≥
eligible date. Status: "Eligible <date>" (violet) before eligible; open > 0 → "Blocked — W-9 missing" (individual
without W-9) or "Payable"; else "Paid up". Pay blocked: "Blocked: collect a W-9 from <referrer> first". Note: "Referral
fees to individuals are reported on Form 1099-NEC. Employee referral bonuses go through payroll as supplemental wages.
Fees to corporations generally need no 1099."
Form: Referrer*, Referrer type (Individual (1099-NEC) / Vendor (corporation) / Employee (via payroll)), Referred
consultant, Fee structure (Per billed hour / One-time after a waiting period), Amount, Cap (hours) or waiting period
(days). Individuals start with W-9 missing.

### 6.18 Payment ledger `[LED]`
"Every payment received and made, newest first. Syncs to the accounting system as the general ledger." KPIs (not
vendor): Received (from clients and primes), Paid out (to sub-vendors), Net cash. Counterparty filter, Export CSV.
Table: Date, Direction (Received / Paid), Counterparty, Invoice, Consultant, Method, Reference, Amount (+/−). Vendor sees
only payments to itself.

### 6.19 Consultants & work authorization `[WA]`
"Everyone working on ESG projects: W-2 employees, 1099 contractors and C2C consultants supplied by vendors." Tools
(admin/legal): Upload former consultants · Former consultants template · Export former. Tabs: **Active (n)** · **Former
— employees, resigned C2C, ended 1099 (n)**.
- Active KPIs: Consultants (n W-2 · n 1099 · n C2C), Work authorization expiring ≤120 days ("Reverify Form I-9 before
  the date", warn), E-Verify cases open, Agreements missing (NDA, offer letter or contractor agreement; bad). Table:
  Consultant (title), Type (· vendor), Project, Work authorization, Valid until (date · n d, colour: ≤60 bad, ≤120
  warn), Form I-9, E-Verify, NDA. Note: "Form I-9 and E-Verify run only after an offer is accepted, never as a
  pre-screen. Work-authorization documents are visible to HR and compliance only; others see the status. For C2C
  consultants the employer (vendor) is responsible and attests in its MSA."
- **Detail**: initials/photo, name, title · location, type, "Open to new projects"; employer, projects (links), skills;
  **Work authorization & compliance**: status, valid until (days), Form I-9, E-Verify, notes (e.g. LCA, I-983), W-9
  (1099); banner if ≤120 days: "Reverify Form I-9 on or before <date>. Reminders go to HR and <name> at 120, 90, 60 and
  30 days."; **Agreements & policies**: offer letter (W-2), ICA (1099), NDA (+ Remind), each required policy; files
  (HR/admin/legal) or "Documents are visible to HR, compliance and company admins."; **Message**; **Offboard**
  (admin/legal).
- **Offboard** form: "Ends the assignment and keeps every record. Use this when an employee leaves, a C2C consultant
  resigns or a 1099 contract ends." Last working day, Reason (Resigned, Assignment ended, Contract completed,
  Terminated, Converted to client employee), Eligible for rehire (Yes/No), **Offboarding checklist** checkboxes: Final
  timesheet submitted and approved · Final invoice / payable created · Client and vendor notified · System and client
  access revoked · Equipment returned · Exit acknowledgment of NDA obligations. → "Offboard and keep records": moved to
  Former; active placements → Ended with end date; removed from project teams; unsubmitted current timesheet removed;
  toast "moved to Former — records kept".
- **Former** KPIs: Former consultants, Eligible for rehire, Left in last 6 months (≤183 days), Form I-9 records
  retained (W-2 count). Table: Name, Type, Employer, Last role, Worked (start – end), Reason, Rehire (Eligible / Not
  eligible), **Records kept until** (W-2: "I-9: <later of start+3 years, end+1 year>"; others "Records: <end+7 years>").
  Note: "Form I-9 is kept for 3 years after hire or 1 year after the end date, whichever is later. Timesheets, invoices,
  payments and agreements are kept for 7 years. Former consultants can't sign in."
- **Former detail**: last role, employer, worked, reason, last client, projects, Sign-in Disabled, I-9 keep-until,
  timesheet history (12 weeks), files, **Rehire — start onboarding** (eligible only) → new onboarding (W-2 → W-2
  contract, C2C, 1099) start in 14 days, flagged rehire.

### 6.20 Clients & vendors `[CO]`
"Companies ESG does business with. The tenant admin adds and maintains them; each vendor can be invited to its own
portal." Toolbar (admin/finance): Upload clients & vendors (active and inactive) · Sample template · Upload old vendor
payments · Export all. Tabs Active / Inactive / All (counts). **Add client or vendor** (admin).
Cards: initials, name, type chip (tenant/Client/Prime vendor/C2C vendor), Inactive chip; Admin, State, EIN (masked),
MSA ids; workforce counts W-2 / 1099 / C2C / Total (vendors & tenant) or "Customer — workforce not tracked here."
List columns: Company, Type, Status, Contact, State, Agreements (or Missing), Next expiry, Open AR, Open AP (masked).
**Detail**: type, status; Admin/contact, State, EIN; end-client relationship note ("End client — ESG works through the
prime vendor; no direct agreement needed"); **Agreements** (days-left chip, id, kind · terms · expires) or "Missing — No
MSA on file. Invoices and payments are blocked until an MSA is signed. **Send MSA**"; **Compliance documents** (status,
doc, expires, what it holds); Billed to them $ / open, Owed to them $ / open (finance); **Payment history before
myTrakIn (imported)** (finance/admin); files (admin/legal/finance); **Status**: Active ("Can receive new SOWs,
invoices and payments." + Mark inactive) or Inactive (since, reason, "Records, agreements and payment history are
kept." + Reactivate).
**Mark inactive** form: warning "n open invoice(s) still need to be settled; they stay trackable after deactivation.";
Inactive from (date); Reason (No active placements, Contract / MSA ended, Project completed, Compliance issue, Other);
"Inactive companies can't get new SOWs or payments, and their users lose sign-in. All history is kept and the company
can be reactivated."
**Add client or vendor** form: Type (Client, Prime vendor, C2C vendor), Legal name*, State, Contact / admin email,
Default payment terms (Net 30, Net 45, Net 60, Pay-when-paid), "Invite to vendor portal (vendors upload W-9, COI and
invoices)". → company status Invited, EIN "Pending W-9", pipeline party stage 1 "Invited — verification pending".

### 6.21 Compliance `[CMP]`
"Missing or expired items block placements and hold vendor payments." Table: Person/company, Type, Requirement,
Expires, Status (Valid / Due soon / Missing / Pending), Effect (e.g. "Payouts held after expiry", "1099 reporting
blocked", "New SOWs blocked after expiry", "Start date at risk", "Referral fee blocked; backup withholding would
apply"). Vendor sees own only.

### 6.22 Document expiry & automatic emails `[CMP]`
"Tracks I-9 reverification, passports, EAD and I-94, insurance certificates, background checks, certifications and
agreements. Emails go out automatically before each expiry." KPIs: Expiring ≤30 days ("Daily emails until resolved"),
Expiring ≤90 days ("Reminders scheduled"), I-9 reverifications due (≤120 days), Emails sent (30 days).
**Automatic email rules** (admin/legal) toggles: Form I-9 reverification (consultant + HR at 120, 90, 60, 30, 14, 7
days and on the date) · Passports (consultant + vendor for C2C — travel and client badge requirements) · EAD, I-94 and
visa notices (consultant + HR + immigration counsel) · Insurance certificates (COI) (vendor/contractor + AP; payouts hold
after expiry) · Other documents and agreements (background checks, certifications, MSAs, SOWs). Note: "Form I-9
reverification covers only work-authorization documents (for example an EAD or I-94). U.S. passports and permanent
resident cards are never reverified — passport dates here are tracked for travel and client-site requirements only."
Buttons **Add document to track**, **Send all due reminders now** (enabled rules, ≤30 days). Table (sorted by expiry):
Person/company, Type, Document, Expires, Status (Expired / n days), Last email, Next email (or Off), Recipients.
Offsets 120, 90, 60, 30, 14, 7, 0 days; next email = first offset date still ahead; expired → today (then weekly).
**Detail**: expiry, email schedule chips (120d · date …, On date), recipients, **Email preview** (Subject "Action
needed: <doc> expires <date>" / "Expired: <doc> for <who>"; body: "Hi <first recipient>, Your <doc> on file with <tenant>
expires on <date> (n days from today). Please upload the renewed document in myTrakIn → My payments & documents → Work
authorization[. HR needs it to complete Form I-9 reverification on or before the expiry date]. This is an automatic
reminder. Reminders go out 120, 90, 60, 30, 14, 7 days before and on the expiry date. Thanks, <tenant> HR & Compliance"),
files, **Mark renewed (+1 year)**, **Send email now**.
**Track a document** form: Person or company, Document (Form I-9 reverification, Passport, EAD card, Form I-94 / visa
approval notice, Driver's license, Certificate of insurance, Background check, Professional certification, Other),
Expiry date*, Also email (comma-separated). → "Tracking started — emails scheduled".

### 6.23 Network & messages `[NET]`
"Connect and message consultants, vendors and people at other myTrakIn companies. Profiles are opt-in; admins control
who can be contacted." Tabs **Feed**, **People**, **Messages**.
- Feed: composer (text, **Attach**, **Post**); posts: avatar, author (→ profile), tag chip (Announcement, Kudos,
  Update), time, text, **Like · n**, **Comment**.
- People: search (skills, names, companies), cards/list: avatar, name, title, organisation (other tenants labelled
  "(myTrakIn tenant)"), skill chips, Open to work, **Connect / Connected**, **Message**, **View profile**.
- Messages: thread list (last message), thread view (from · time · text), composer with **File** attach and **Send**.
  Footer "Messages are retained per your company's policy and are not used for hiring decisions."
*Superseded*: first version "Community — visible to <tenant> only".

### 6.24 Users & security `[USR]`
"Who can sign in, how they sign in, and what they can do." Tabs: **Users**, **Sign-in & MFA**, **SSO & provisioning**,
**Roles & permissions**.
- Users: **Invite user** (admin); table User (External chip), Role & scope, Reports to, Sign-in (SSO (Entra ID) / Email
  one-time code / Personal email + code / Mobile number (SMS code)), Second factor (Passkey / Authenticator app / SMS
  code), Last active, Status (Active / Invited / Locked 15 min / Deactivated) + **Unlock**. Footer "Seats in use: n
  internal users. External users (vendor admins, consultants, contractors) are free on the Growth plan."
- User row → **admin user panel**: avatar, role · reports to, status, sign-in, second factor, last active, last sign-in
  IP · location, active sessions; recent sign-ins (when, IP, location, result); actions **Send password reset**, **Reset
  two-step verification**, **Sign out everywhere**, Unlock, **Deactivate / Reactivate**, View profile.
- Sign-in & MFA toggles: Single sign-on (SAML/OIDC; "Required for @company domain users once enabled") · Email one-time
  code (6-digit, 10-minute expiry, 5 attempts then 15-minute lock) · Mobile number (SMS code) · Passkeys (WebAuthn;
  phishing-resistant) · Allow personal email for external users · Passwords (off by default — passwordless only) ·
  Require MFA for admins, finance and approvers (authenticator or passkey; SMS not accepted) · Require MFA for everyone ·
  Restrict admin sign-in to office / VPN IP ranges. Session timeout (30 minutes idle / 8 hours / 12 hours).
  Re-authenticate before (Payments, bank-detail changes and exports / Payments only).
- SSO & provisioning: Identity provider (Microsoft Entra ID (OIDC)), Verified domains (esg.example.com — Verified · DNS
  TXT), Enforcement (Required for verified-domain users), Break-glass account (1 admin with passkey, monitored), **Test
  connection**; **User provisioning (SCIM)** toggle "Provision and deprovision users from Entra ID — Leavers lose access
  within minutes of being disabled in the directory."; group mapping VC-Finance → Finance, VC-Legal → Contracts / legal,
  VC-AM → Account manager.
- Roles & permissions: access matrix (§2).
- Invite user form: Name, Email, Role (Finance (AR/AP), Account manager, Contracts/legal, HR & compliance, Approver
  (timesheets), Viewer, Company admin), **Scope** (All clients / <client> only …), Reports to (internal users).
*Superseded*: first "Roles & access" page listed **Payment authority** per user (e.g. "Approve runs", "Unlimited",
"Runs up to $100k", "None") — keep as the approval-limit field.

### 6.25 Approvals & hierarchy `[APR]`
"Reporting lines decide who approves what. Delegation covers time off without losing the audit trail."
**Organisation** chart (tree with initials, name, title; e.g. President · company admin → Technical Lead · tenant
admin → Account manager, Delivery managers (timesheet approvers); Finance manager → AP specialist, AR specialist
(collections); Contracts & legal · signatory ≤ $250k; HR & compliance). **Approval chains** table (§10.5).
**Delegation**: Scheduled chip "K. Reddy → Madhavi Gonnala · Oct 20–24 · all finance approvals" + **Add delegation**
(admin).

### 6.26 Audit log `[AUD]`
"Every change to data and every sign-in, approval, export and file action. Entries are append-only and kept for 7
years." Search, **Export**. Table: When (date, time), User, Action chip (warn for Removed/Rejected/blocked/Disabled),
Record, Change, Source (e.g. "Web · Chrome/macOS", "Vendor portal", "Safari/iOS", "Web (this session)").
Examples: Updated SOW rate $80 → $82; Uploaded vendor invoice PDF; Sent for signature; Change requested (bank account,
pending dual approval); Role changed (Viewer → Account manager, scope Atlas Foods); **Sign-in blocked** ("5 failed
one-time codes — locked 15 min"); Removed file ("kept 30 days in trash"); Exported (CSV, 128 rows).
Actions that must be audited (from prototype hooks): recorded payment (balance before → after), approved payment run,
resolved exception, scheduled payment, added company, timesheet submit/approve/reject/bulk, collection note,
uploads/removals, invites, registration decisions, onboarding steps, policy acceptance (IP & device), e-sign events,
imports/exports/template downloads, profile changes, preferences, password/MFA/session changes, AI questions.

### 6.27 Data import & export `[DATA]`
"Bring data in from spreadsheets, QuickBooks or an old tracker, and take any data out as CSV. Every import is
validated row by row and recorded in the audit log." **Import data**, **Export everything (n CSV files)**.
Table: Data, Columns (required listed), Records now, **Download template**, **Import**, **Export CSV**. Import history:
When, By, Data, File, Rows, Imported, Result ("Imported" / "Imported — n rows skipped").
**Import drawer**: "Upload a CSV (or Excel saved as CSV). Use the template so the columns match; we check every row
before anything is saved." What are you importing? (select); column list with required in bold; Download template,
Choose CSV file, Try with sample data. **Preview**: missing required columns banner; Rows ready / Rows with errors;
first 25 rows (row no, first 4 columns, check chip with first error +n); checkbox **Update existing records that
match** (default on); **Import n rows**. Row checks: required present; columns with "date" → YYYY-MM-DD; amount, rate,
value, hours, Sun…Sat, ceiling → number; email → valid email. Bad rows never block good rows. Natural keys: consultant
name, company legal name, project name, agreement ID, SOW ID, invoice number. Consultant rows with status Active are
activated immediately; Former/resigned/inactive/ended/terminated go to Former. Company rows with Existing MSA ID create
the MSA (supplier/buyer from type), W-9 = N creates a "W-9 Missing" compliance item, COI expiry creates a COI item
(Expired / Due soon ≤45 d / Valid); Inactive status sets inactive date/reason. SOW rows create a placeholder MSA if
missing ("Imported — upload signed copy"). Result toast "n new, n updated, n skipped".
Footer: "Imports never include other parties' rates: placements carry only ESG's AR bill rate and AP rate. Sensitive
fields (SSN, bank accounts) are not accepted in CSV; collect them on W-9 and bank forms."
**Per-page toolbar** (admin/finance; import button for admin, and for finance on AR/AP/payments/timesheets) on pages
with importable data: "<entity>: Sample template · Import · Export". Templates & columns: §10.7.

---

## 7. Consultant portal ("My payments & documents") `[ME]`
Header: name, title · type ("C2C through <vendor>" / "W-2 employee of ESG" / "independent contractor"). *Demo persona
switch (Ravi C2C, Anita W-2, Daniel 1099).* **To do · n** (Action chips): Sign NDA · Accept: <policy> · Submit
timesheet for week of … · Upload work authorization renewal (expires …) (≤120 days).
Tabs: **Payment status** · **Projects, chain & SOW** · **Work authorization** · **Company policies & documents** ·
**Timesheet history** · **Expenses & time off**.
- Payment status: "Follow each month from your approved timesheet to payment. Amounts are not shown here." Per period
  (newest first): period, project · hours, chip "Waiting at: <step>" or "Paid" / "Paid to <employer>"; steps:
  ✓ Timesheets approved (Hours locked) → ✓ Invoice sent to <customer> (date) → <customer> pays ESG (Paid <date> /
  Overdue — ESG is following up / Part paid / Due <date>) → **W-2**: "You are paid through payroll — Your pay does not
  wait for the customer" (customer step informational only); **1099/C2C**: ESG pays you/<employer> (Paid / "Waiting for
  the customer to pay ESG (pay-when-paid)" / "Hours on the vendor invoice don't match approved timesheets — being
  corrected" / Scheduled for / Due) → C2C: "<employer> pays you — Handled by your employer — ask them for the date".
  Plus "This week" timesheet status + Open ("Approved timesheets are invoiced at the end of the billing period.").
- Projects, chain & SOW (per placement incl. completed): project, status, role; **How money flows to you** (End client →
  Prime vendor/Customer → Staffing partner → Your employer → You; names only) + sentence per type ("ESG pays you through
  payroll on the regular pay dates, whether or not the customer has paid." / "ESG pays your invoices directly (Net
  15)." / "ESG pays <vendor> (terms); <vendor> pays you under your own agreement with them."); **Assignment & SOW**:
  assignment dates, time left (days, coloured) or Completed, governing SOW (vendor SOW if any) with dates, customer SOW
  end if different, extension status; **Your contacts**: ESG manager, timesheet approver (ESG admin), employer contact
  (C2C). Footer: rates are confidential.
- Work authorization: status, valid until (days left), Form I-9, E-Verify, notes; renewal banner "Upload your extension
  or new document before <date> so HR can reverify Form I-9 on time. Reminders: 120, 90, 60 and 30 days before.";
  C2C text "Your employer, <vendor>, completes your Form I-9 and confirms your eligibility to ESG. Contact them for
  changes."; 1099 text "Independent contractors don't complete Form I-9 with ESG. Keep your W-9 up to date."; files
  ("Only you and ESG HR / compliance can see these files.").
- Company policies & documents: **Policies to accept** table: Policy, Version, Effective, Applies to, Your status (Not
  required / Accepted <date> / Pending), Read, **Accept** ("Accepting records the date, version, IP address and
  device."); **Your signed agreements** (NDA — View / Sign now; Offer letter (W-2); ICA (1099)); **Company documents**
  (Document, For, Updated, Download) filtered by type (§10.8).
- Timesheet history: filters project (n), month, status, search; Export CSV; KPIs Weeks shown, Hours, top 2 projects'
  hours; table Week, Project, Hours, Status, Approved by, Billing; "Show more" (20 at a time). "Each project is a
  separate line, so a week on two projects shows twice."
- Expenses & time off: **My expenses** (Submit expense) table Date, Category (+ "Billable to client"), Project, Amount,
  Status (+ note e.g. "Reimbursed by BrightPath"); text per type: C2C "Approved expenses are paid to your employer, who
  reimburses you." / 1099 "Approved expenses are added to your next invoice payment." / W-2 "Approved expenses are
  reimbursed in payroll."; **Time off & holidays** (Request time off) table Dates, Type, Status (Holiday / Requested /
  Approved / Declined); "Approved time off is pre-filled on your timesheet and your client approver is notified."
- Submit expense form: Date, Category (Travel — client site, Mileage, Lodging, Meals (travel), Certification exam,
  Other), Project (active placements), Amount*, Billable to client (per SOW), Receipt → approval item "ESG admin".
- Request time off form: Type (PTO, Sick leave, Unpaid leave), From*, To*, Note for approver → approval item.
- **My timesheet** (consultant's Timesheets page): week, n active projects; returned banner with reason; grid per
  project (inputs Sun–Sat, row total, Remove row), Daily total; **Add project row** (active placements + internal);
  stepper You (enter and submit hours) → ESG admin (validates and approves) → Locked (feeds invoicing); "Reminders Friday
  3:00 PM and Monday 9:00 AM until you submit."; **Save draft**, **Submit week** ("Enter your hours first"); locked text
  "Submitted — waiting for ESG admin." / "Approved and locked."; link to Timesheet history.

---

## 8. My profile & settings `[USR][NET-05]`
Tabs (own profile): **Profile** · **Account & security** · **Notifications** · **Preferences** · **Privacy & data**.
Other people's profile: Profile only + ← Back. Header subtitle "<role label>. Your profile is what colleagues, clients
and vendors see on the network."
- **Profile**: cover image (Edit cover), photo (Upload/Change/Remove; resized), name, headline (or "Add a headline"),
  location · n connections, chips Open to new projects + org/role; own: **Edit intro** (Name, Headline, Location, Phone,
  Website or portfolio, Open to new projects) + visibility label; others: Connect/Connected, Message. Sections with
  add/remove (own): **About** (Edit; placeholder "Tell people what you do best, the industries you know and what you are
  looking for."), **Experience** (Title*, Company/project, From, To (blank = present), Description), **Skills** (Skill*;
  n endorsements; others can **Endorse**/Endorsed), **Licenses & certifications** (Name*, Issuer, Year, Credential),
  **Education** (School*, Degree/field, Year), **Activity** (own posts, likes; "Write a post"). Side: **Profile strength
  %** with top 3 to-dos (8 items: photo, headline, about, experience, ≥3 skills, certification, education, location);
  **Contact info** (email, phone, website — own or connections if allowed; else "Visible to connections only.");
  **People you may know** (3 not-connected). Consultant profiles are seeded from consultant record and placements
  (experience).
- **Account & security**: Email, phone & password — sign-in email (**Change**: new value + code; notice to old),
  mobile (Change), password last changed; Current / New / Confirm, strength meter (Too weak…Very strong) and rules (≥12
  characters, letters and numbers, not a known breached password, not your name); **Forgot password? Email a reset
  link**; **Update password** (errors: current missing; 12+ with letters & numbers; breached; same as current; mismatch)
  → other sessions signed out + confirmation e-mail. Note: "Used when your company allows password sign-in. Passwords are
  stored as salted hashes and checked against known breaches; changing it signs out your other sessions."
  **Two-step verification** list (On: Authenticator app, Passkey — device; Remove), Backup "Text message +1 ••• •••
  2030 · not accepted for admin and finance roles"; **Add passkey**, **Add authenticator app** (QR, setup key, 6-digit
  verify), **Recovery codes** (10 one-time codes; generating new cancels old; Copy, Download).
  **Where you're signed in**: Sign out all other sessions; table Device, IP, Location, Last active, This device / Sign out.
  **Recent sign-in activity**: When, Method, IP, Location, Device, Result (Success / Blocked — "new country, MFA not
  passed"). "Don't recognize something? **Report it and sign out everywhere**."
- **Notifications**: matrix events × channels (Email, SMS, In-app, Mobile push). Events: Approval requests, Timesheet
  reminders, E-signature requests, Invoices paid or overdue, Payments sent to me / my company, Document expiry (I-9,
  passport, insurance), Messages and connection requests, Policy updates, Weekly summary. Email digest (Send each one
  right away / Daily digest at 8:00 AM / Weekly digest on Monday); Quiet hours (no SMS or push) from–to; Save. "Security
  alerts (new sign-ins, password and MFA changes) are always sent by email."
- **Preferences**: Language (English (US), English (UK), Español, Français, हिन्दी), Time zone (America/New_York,
  America/Chicago, America/Denver, America/Los_Angeles, Asia/Kolkata, Europe/London), Date format (Oct 11, 2026 /
  10/11/2026 / 11/10/2026 / 2026-10-11), Start page after sign-in (Dashboard, My approvals, Timesheets, Payment flow,
  E-signatures), Default view for lists (List / Cards), Theme (System / Light / Dark), Table density (Comfortable /
  Compact); Save (applies immediately; audited).
- **Privacy & data**: Who can see your profile (Everyone on myTrakIn / My company and connections / Only my company);
  Who can message you (Everyone / Connections / Only my company); Show email and phone to connections; "Pay, rates, SSN,
  bank and immigration details are never shown on profiles."; Open to new projects ("Recruiters at your company and
  connected firms can see this."); **Download my data** (profile, timesheets, documents you uploaded, signatures and
  sign-in history — JSON + files); **Electronic records consent** (given <date> when signing <envelope>) + **Request
  paper copies**; **Close my account** (external users: "Your profile is removed; records the law requires (timesheets,
  tax forms, signed agreements) are kept for the retention period." + Request; internal: "Managed by your company
  admin.").
- **Account menu** (avatar): photo, name, role label; View my profile, Account & security, Notifications, Preferences,
  Privacy & data, Sign out.

---

## 9. Cross-cutting behaviour

### 9.1 Tables, cards, files `[UX]`
- Every table with ≥2 rows: clickable sortable headers (▲/▼/⇅; numbers, money, dates sorted correctly; Total rows stay
  last); with ≥4 rows a toolbar: search, up to 4 column filters (columns with 2+ distinct short values), Sort by… menu,
  Clear, row count "n of N rows", **List / Cards** switch, **Export CSV** (exactly the visible rows).
- Cards view: first column as title (avatar on people pages), other non-empty columns as label/value, row buttons
  copied, card click = row click, keyboard Enter opens.
- Card-first pages (Clients & vendors, Projects, Network people): search, type filter, sort A–Z / Z–A, list/cards.
- Default view from Preferences.
- **Files block** on records (companies, consultants, projects, MSAs, SOWs, new hires, former consultants, document
  expiry): "Files (n)", list or **Thumbnails** (images show previews; other files show extension), Download/Open, Remove
  ("Removed — recoverable for 30 days"), **Add files** (multi; "File added — virus-scanned and encrypted"); audited.

### 9.2 Global search, alerts `[UX-02][UX-03]`
- Search (≥2 characters, top 10): platform → tenants (plan · status); tenant roles → invoices ("Client invoice ·
  person · period" / "Payee invoice …"), SOWs (role-visible), MSAs, consultants, projects, companies. "No matches — Try an
  invoice number, SOW, person or company".
- Alerts drawer "Alerts & reminders — n items need attention" (Open each) or "You're all caught up.": platform → sign-ups
  pending/needs info + stalled tenants; consultant → own to-dos; vendor → e.g. "COI expires Oct 31 — Upload renewal to
  keep payouts flowing"; admin/finance/legal/AM → every approval ("Approval: <type>") + every *bad* missing item.

### 9.3 Missing-items engine `[DASH-05][AGR-06]`
Excludes inactive companies and former consultants. Items:
- Company (not end-client-only, not the tenant) with no MSA → bad "No MSA on file".
- Vendor / referrer documents not Valid → bad if Missing else warn ("<doc>: due soon (<date>)").
- W-2 consultant without signed offer → bad; 1099 without signed ICA → bad; any consultant NDA not signed → bad.
- Required policies not accepted → warn "Not accepted: <list>" (W-2: all 4; others: code of conduct, info security,
  timesheet & expense).
- Work authorization ending ≤120 days → warn (≤60 bad) "<type> ends <date> (n days) — I-9 reverification".
- Timesheet not submitted this week → warn.

### 9.4 Smart suggestions & AI assist `[AI]`
Header **AI assist** drawer: "Suggestions use only data you're allowed to see. Nothing is sent or changed without your
click." **Suggested next actions · n** (title, why, action button) + **Ask a question** box with quick prompts:
"Which invoices are overdue?", "What documents expire soon?", "Who is available for a new project?", "Summarize this
page". Every question is audited. (Prototype uses rules; production: LLM with retrieval over the tenant's data, same
scoping.)
Suggestion rules:
- Platform: re-engage stalled tenants ("Stuck at '<next step>' with no activity since … usually need help uploading
  MSAs" → Send check-in); review flagged sign-ups ("Pattern matches past fake sign-ups").
- Consultant: own to-dos; renew documents expiring ≤120 days (→ Upload).
- Finance/admin/AM: collect overdue AR ("<inv> is n days late and part-paid… a call plus a written reminder usually
  clears the balance within 2 weeks" → **Draft email**).
- Finance: accept AP exceptions at approved hours (→ Accept).
- Visible supplier SOWs ≥90 % burn ("runs out within one billing cycle"; nudge client about amendment → Open SOW).
- Vendor SOWs with only a draft flow-down amendment ("Without it, <consultant> can't be paid after that date").
- Bench consultant (internal project) for a placement ending soon, with overlapping skills (→ View profile).
- I-9 reverification for work-auth docs ≤60 days ("Ask for the extension receipt now").
- Finance/admin: lowest W-2 margin below 18 % target ("Review <name>'s rate at renewal" → Open payroll).
- Missing timesheets this week ("Missing time delays the <date> invoice run" → Remind).
Ask answers (plain text bullets) for: overdue/late/collect; expiry/I-9/passport/EAD/visa (≤120 days); bench/available;
margin/profit (finance/admin only); timesheets/missing; SOWs ending (≤60 days); summarize this page (title + KPIs);
otherwise a help sentence listing what it can answer.
**AI-drafted follow-up** (from overdue suggestion): drafted subject "<inv> — remaining balance of $x" + body from
invoice, payments and notes (thanks for partial payment of $y received <date>, remaining balance was due <date> and is
n days past due, ask to confirm payment date, signed by finance); "Edit before sending"; buttons Make it firmer, Make it
friendlier, Send.

### 9.5 Notifications & reminders `[NOT]`
All e-mails land in the **Reminders sent** log (When, To, Reminder, Channel). Rules §10.4.

---

## 10. Reference lists

### 10.1 Onboarding checklists
- **W-2 full-time employee**: Offer letter signed · Form I-9 Section 1 (by day 1) and Section 2 (within 3 business days)
  · E-Verify case created · W-4 and state withholding · Direct deposit · Benefits enrollment · NDA signed · Company
  policies accepted · Background check · Projects assigned & timesheet access
- **W-2 contract (hourly)**: Contract employment offer signed · Form I-9 Section 1 and Section 2 · E-Verify case created ·
  W-4 and state withholding · Direct deposit · NDA signed · Company policies accepted · Background check · Projects
  assigned & timesheet access
- **C2C**: Vendor has an active MSA with ESG · Vendor SOW / work order signed · Employer attests work authorization ·
  Vendor insurance (COI) covers consultant · NDA signed by consultant · Company policies accepted · Background check ·
  Projects assigned & timesheet access
- **1099 contractor**: Independent contractor agreement signed · W-9 received and TIN matched · Classification review
  (1099 vs W-2) documented · Certificate of insurance (if required) · NDA signed · Company policies accepted · Projects
  assigned & timesheet access

### 10.2 Stage lists
- Party onboarding (8): Registered · Verified · MSA / ICA / offer · SOW / work order · Digitally signed · Project set up ·
  Timesheets live · Invoicing live
- Tenant onboarding (8): Tenant created · Admin invited · Admin activated (MFA) · Company profile complete · Clients &
  vendors added · MSAs / SOWs uploaded · First invoice tracked · First payment recorded — live

### 10.3 Statuses
- Hop/invoice: §3. Timesheet: Not submitted, Submitted, Approved, Rejected. Placement: Active, Ending soon, Onboarding,
  Completed, Ended. Company: Active, Invited, Approved — agreement next, Imported — MSA needed, Active (imported),
  Inactive. Registration: Pending, Approved, Rejected (+ info requested). Sign-up: Pending, Needs info, Approved,
  Rejected. Envelope/signer: §6.7. Expense: Submitted, Approved, Rejected. Time off: Requested, Approved, Declined,
  Holiday. Document: Valid, Due soon, Missing, Pending, Expired. Tenant: §5.1. User: Active, Invited, Locked 15 min,
  Deactivated. New hire: Onboarding, Ready, Active. Referral: Eligible <date>, Payable, Blocked — W-9 missing, Paid up.
  Subscription invoice: Paid, Due <date>, Overdue 60+ days. Credit note: Open — apply to next payment (→ applied).

### 10.4 Reminder rules (Area — Rule — Channel — default on)
1. Timesheets — Remind consultant Friday 3:00 PM if the week is not submitted — Email + SMS — on
2. Timesheets — Second reminder Monday 9:00 AM; escalate to vendor admin / manager Tuesday — Email — on
3. Client invoices (AR) — Courtesy notice 7 days before the due date — Email to customer AP — on
4. Client invoices (AR) — Overdue reminders at +1, +7 and +15 days; +15 copies the account manager — Email — on
5. Client invoices (AR) — +30 days: escalate to finance head and flag for stop-work review — Email + task — on
6. Vendor / 1099 invoices (AP) — Notify payee when an invoice is matched, held, scheduled and paid — Email + portal — on
7. Agreements — Unsigned e-signature envelope: remind every 3 days, escalate after 9 — Email — on
8. Contracts — MSA / SOW expiry alerts at 90, 60 and 30 days — Email + task — on
9. Compliance — Work authorization / I-9 reverification alerts at 120, 90, 60 and 30 days — Email to HR + consultant — on
10. Compliance — Passport, EAD, I-94 and certification expiry emails at 120, 90, 60, 30, 14, 7 days and on the date —
    Email to person + HR (+ vendor for C2C) — on
11. Compliance — Vendor COI / W-9 expiry at 30 and 7 days; hold payouts after expiry — Email — on
12. Policies — New policy version: ask every affected person to accept within 14 days — Email + in-app — on
13. Referrals — Notify finance when a referral fee becomes payable — Task — **off**

### 10.5 Approval chains (defaults)
| Item | Chain |
|---|---|
| Timesheet | Consultant submits → ESG admin validates and approves |
| Client invoice (AR) | Created from approved time → Finance review → Sent |
| Vendor / 1099 invoice (AP) | AP specialist (three-way match) → Finance manager ≤ $25,000 → Company admin above |
| Payment run | Finance manager → Company admin (dual approval above $25,000) |
| SOW / amendment | Account manager → Legal → Finance (if margin < 15%) → Authorised signatory |
| MSA / contractor agreement / offer letter | Legal → Company admin → e-signature |
| Bank detail change | Requester → Finance manager + phone callback to known contact |
| New registration | Compliance verification → Company admin |
| Referral fee | Finance manager → Company admin (above $2,500) |
| Rate change | Account manager → Finance manager |

### 10.6 Registration documents
- Staffing company: Certificate of incorporation / formation · IRS EIN letter (CP 575 or 147C) · Photo ID of authorised
  signatory
- Vendor: Certificate of formation · W-9 · Certificate of insurance (GL, E&O) · Bank letter or voided check
- Client: W-9 · Accounts payable contact sheet
- 1099: W-9 · Resume · Professional liability insurance (optional)
- Consultant: Resume · Photo ID (W-2 hires complete Form I-9 after offer acceptance)

### 10.7 Import / export templates (columns; required = *)
| Key | Label | Columns |
|---|---|---|
| consultants | Consultants | Full name*, Email*, Mobile, Engagement type*, Employer (C2C only), Job title, Start date*, Work location, Project IDs (; separated), Hours per week (; separated), Status (Onboarding / Active), End date (former only), Reason for leaving, Eligible for rehire (Y/N) |
| companies | Clients & vendors (incl. existing vendors) | Legal name*, Type (Client / Prime vendor / C2C vendor)*, EIN, State, Contact name, Contact email*, Default payment terms, Existing MSA ID, MSA effective date, MSA expiry date, W-9 on file (Y/N), COI expiry date, Status (Active / Inactive), Inactive since, Inactive reason |
| projects | Projects | Project name*, Client*, Prime vendor (if any), SOW IDs (; separated), Start date, End date, ESG manager, Client timesheet approver, Description |
| placements | Placements & rates (AR / AP only) | Consultant*, Project ID*, Customer (who ESG bills), AR bill rate*, AR SOW / PO, AR terms, Payee (vendor or 1099), AP rate, AP SOW, AP terms, Start date*, End date |
| sows | SOWs & work orders | SOW ID*, MSA ID*, Counterparty*, Side (We bill / We pay), Title, Consultant(s), Start date*, End date*, Value (ceiling) |
| msas | MSAs & contractor agreements | Agreement ID*, Type, Counterparty*, ESG is (Supplier / Buyer), Effective date*, Expiry date*, Payment terms, Renewal, Notice period, Insurance required |
| timesheets | Timesheets (bulk upload) | Consultant*, Week starting (Sunday)*, Project ID*, Sun, Mon, Tue, Wed, Thu, Fri, Sat, Notes |
| arinv | Client invoices (AR) | Invoice number*, Customer*, SOW / PO, Consultant, Period, Hours, Rate, Amount*, Issued, Due date*, Status |
| apinv | Vendor & 1099 invoices (AP) | Invoice number*, Payee*, SOW, Consultant, Period, Hours invoiced, Rate, Amount*, Terms, Status |
| payments | Payments received / made | Date*, Direction (In / Out), Invoice number*, Counterparty, Amount*, Method, Reference |
| expenses | Expenses | Consultant*, Date*, Category, Project ID, Amount*, Billable (Y/N), Status |
| users | Users | Name*, Email*, Role*, Scope, Reports to, Sign-in method |
| vendorHistory | Old vendor payment history | Vendor*, Invoice number*, Period, Consultant, Amount*, Paid date*, Reference |
| formerConsultants | Former consultants (employees, C2C, 1099) | Full name*, Engagement type*, Employer, Last job title, Start date*, End date*, Reason for leaving, Eligible for rehire (Y/N), Last client, Projects (; separated) |

The product additionally has templates for expiring documents and W-2 payroll (functional §3.13) — keep them.

### 10.8 Policies & company documents
Policies: Code of conduct v2 (eff. 2026-01-01, everyone) · Information security & acceptable use v3 (2026-10-01,
everyone) · Anti-harassment policy v1 (2025-01-01, W-2 employees) · Timesheet & expense policy v2 (2026-01-01,
everyone). Company documents: Consultant handbook 2026 (everyone) · Holiday calendar 2026 (everyone) · Expense
reimbursement guide (W-2 and 1099) · Benefits guide 2026 — medical, 401(k), PTO (W-2) · Remote work & equipment
guidelines (everyone).

### 10.9 Constants
1099-NEC threshold $2,000 (2026 payments; configurable) · forms due Jan 31 · backup withholding 24 % · employer tax
estimate 8.65 % · W-2 margin target 18 % · SOW burn warn 75 % / alert 90 % · SOW ending window 60 days · MSA expiring
window 90 days · work-auth window 120 days · document e-mail offsets 120/90/60/30/14/7/0 · AR reminder offsets −7, 0,
+1, +7, +15, +30 (+45, +60) · envelope expiry 30 days, reminder every 3 days, escalate after 9 · OTP 6 digits, 10
minutes, 5 attempts, 15-minute lock · tenant stalled after 14 days inactive · trial 14 days · support access 30 minutes ·
suspension after 60 days unpaid · file trash 30 days · audit retention 7 years · I-9 retention later of hire+3 y /
end+1 y · other records 7 years · approval thresholds $25,000 (AP, payment runs), $2,500 (referrals), margin 15 %
(SOWs), signatory limit example $250k · timesheet max 12 h/day, W-2 overtime > 40 h at 1.5×.

---

## 11. Demo data (for seed.sql / tests)

Companies: **Meridian Pharma Inc.** (end client, NJ, via prime — no direct agreement) · **Northwind Consulting** (prime
vendor, NY, MSA-NW-ESG, Net 45) · **Atlas Foods Corp.** (client, TX, MSA-AF-ESG, Net 30, auto-renew) · **BrightPath
Tech LLC** (C2C vendor, NJ, MSA-ESG-BP, pay-when-paid / Net 30; COI expires Oct 31) · **Orion Data Partners** (C2C
vendor, IL, MSA-ESG-OD expires Dec 31 renewal pending; W-9 missing) · **Nova Analytics Inc.** (client, approved, MSA in
draft) · inactive: Pinewood Tech LLC (vendor), Harbor Retail Group (client) · registrations: Silverline Staffing LLC
(vendor, COI + bank outstanding), Meera Iyer (1099, gmail, unverified).
Consultants: **Ravi Kumar** (C2C via BrightPath; two placements PL-1042 Meridian via Northwind $95 AR / $80 AP
pay-when-paid, PL-1057 Atlas $105 / $82; plus completed PL-0991) · **Anita Desai** (W-2, H-1B reverify Nov 20, PL-1063
$84) · **Marcus Hill** (C2C via Orion, PL-1071 Atlas $120 / $99, ending soon) · **Grace Okafor** (W-2, onboarding, NDA
not signed, PL-1078 $88) · **Daniel Cho** (1099, PL-1084 Atlas $85 / $65 Net 15) · **Priya Nair** (W-2, STEM OPT EAD
Dec 5, bench on internal project). Former: Sanjay Mehta (W-2), Olivia Chen (C2C Pinewood), Tom Becker (1099), Rita
Alvarez (C2C, not rehire-eligible). New hires: Kavya Rao (W-2 FT, 2 projects), Luis Ortega (W-2 contract), Ethan Brooks
(C2C BrightPath, 2 projects), Meera Iyer (1099).
Projects: PRJ-01 S/4 Security Rollout (Meridian via Northwind) · PRJ-02 GRC Audit Support (Atlas) · PRJ-03 Supplier
Portal (Atlas) · PRJ-04 ESG Accelerator (internal).
Key invoices: ESG-AR-2026-0371 Northwind Jul, part paid $8,000 by check, overdue with collection notes ·
BP-INV-1187 held on ESG-AR-2026-0412 · BP-INV-1188 exception (72 billed vs 64 approved) · OD-0342 scheduled Oct 30 ·
credit note ESG-CN-2026-0007.
Tenant users: Madhavi Gonnala (President, company admin, signatory), Praveen Gottimukkula (tenant admin), K. Reddy
(finance manager), J. Lopez (AP specialist), N. Patel (legal, signatory ≤ $250k), S. Iyer (AM, Atlas Foods scope), A.
Brown (HR & compliance), external S. Rao (BrightPath), consultants.
Platform: 15 tenants (T-001 ESG … T-015) across plans and statuses (incl. suspended Old Mill Contractors, trials,
stalled Lakeshore Tech Staffing); sign-ups Crestview IT Partners, Brightwave Consulting Group, QuickHire Temps (flagged).
