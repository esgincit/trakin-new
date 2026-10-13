# myTrakIn training guide

Version 1.0 · October 2026 · For trainers, implementation consultants and new customers.

The exercises use the **demo workspace** (*Executive Software Guild Inc.*) loaded by `supabase/seed.sql` into a
**staging or training** environment — never production. Reset it between classes by re-running the seed on a fresh
database (see [deployment.md § Training environment](deployment.md#training-environment)).

## Training plan

| Session | Who | Length | Outcome |
|---|---|---|---|
| 0. Orientation | Everyone | 20 min | Sign in with a code, set up MFA, find your way, understand AR/AP-only |
| 1. Consultant self-service | Consultants (or the HR people who support them) | 20 min | Submit a timesheet, accept a policy, read payment status, request time off |
| 2. Timesheet approval | Approvers, account managers | 30 min | Review checks, approve, return, bulk approve |
| 3. Invoicing & collections | Finance | 60 min | Create invoices from timesheets, send, record payments, follow up |
| 4. Payables | Finance | 45 min | Three-way match, pay-when-paid, payment runs, 1099, referrals, payroll |
| 5. Onboarding & compliance | HR, legal | 60 min | Onboard each engagement type, I-9 / work authorization, documents, policies, registrations |
| 6. Contracts & e-signatures | Legal, account managers | 45 min | Record and create MSAs/SOWs, amendments, send and track signatures |
| 7. Administration | Admins | 45 min | Users and roles, import/export, reminders, audit, settings, go-live checklist |
| 8. Vendor portal | Vendor contacts (optional webinar) | 15 min | See consultants and timesheets, submit invoices, read statuses |
| 9. Owner console | Platform team | 30 min | Approve sign-ups, create workspaces, track usage and revenue |

Each session: 10-minute demo by the trainer → hands-on exercises → 5-question check. Trainees need one browser tab
signed in as their training role (trainers create one user per role per trainee with *Users & roles → Invite user*).

---

## Session 0 — Orientation

**Key idea: AR/AP only.** Draw the chain on the whiteboard: Meridian (end client) → Northwind (prime) → ESG (you) →
BrightPath (C2C vendor) → Ravi (consultant). ESG tracks two links: Northwind → ESG (AR) and ESG → BrightPath (AP).
Meridian → Northwind is not ESG's contract: it appears by name with `••••`.

Exercises
1. Sign in with *E-mail me a code*. Add an authenticator app if asked.
2. Switch the theme (Auto/Dark/Light). Open *Account & security* and set table density to Compact.
3. Open **Consultants**: search "SAP", filter Type = C2C, sort by Location, switch to **Cards**, then **Export**.

Check
1. Why does the Meridian card show `••••`? *(Not your contract — never stored.)*
2. Where do you change how a list looks? *(List/Cards toggle; it's remembered.)*
3. Which roles must use two-step verification? *(Admin, finance.)*

## Session 1 — Consultant self-service

Sign in as **ravi.kumar@example.com** (C2C via BrightPath, two projects).

1. **My work**: name both projects and the chain for each. Which SOW ends first?
2. **Where my payments are**: for the latest period, has the customer paid? Has BrightPath been paid?
   (You see status and dates only.)
3. **My timesheet**: enter 5 h Mon–Thu on *S/4 Security Rollout* and 3 h Mon–Thu on *GRC Audit Support*; **Save draft**;
   then **Submit week**. Try to edit it again — why can't you?
4. **Policies & documents**: open *Information security v3*, then **Accept**.
5. **Expenses & time off**: submit a $45 parking expense on GRC Audit Support; request one day of PTO next month.

Check: Can Ravi see his bill rate? *(No.)* What happens if he forgets to submit? *(Reminders Fri/Mon/Tue; HR copied Tuesday.)*

## Session 2 — Timesheet approval

Sign in as an **approver** or **finance** user.

1. **Timesheets** → this week. Which rows say *n to review*? Open one and read each check.
2. Approve Ravi's week (from Session 1).
3. Open Anita's week → **Return for changes**: "Friday is a company holiday — please move hours."
4. Go to last week → **Approve all that pass**. Which were skipped and why?
5. **History** tab: filter Consultant = Ravi Kumar, Status = approved. Export.

Check: What does "within weekly allocation" compare? *(Hours logged vs hours/week on the placements.)* When does
overtime apply? *(W-2 over 40 h in the week.)*

## Session 3 — Invoicing and collections (finance)

1. **Dashboard**: read the KPIs and the top three smart suggestions. Which customer is late, and by how many days?
2. **Invoices → Create invoices from timesheets** for last week. How many drafts were created? Run it again — why
   is nothing new created?
3. Open a draft → **Send to customer**. Check **Compliance → Reminders & e-mails** — find the e-mail in the log.
4. **Payment flow**: find Ravi's S/4 row. Which hop is held, and why?
5. Open the overdue Northwind invoice → add a follow-up note → record a **part payment** of $5,000 by ACH.
   What is the new status?
6. Record the rest. Go back to **Payment flow** — what happened to the matching BrightPath invoice?
   *(Pay-when-paid released → Ready to pay.)*

Check: When does finance get copied on reminders? *(30 days late.)* Can you void an invoice with a payment? *(No.)*

## Session 4 — Payables, payroll, 1099, referrals (finance)

1. **Invoices → AP**: open BP-INV-1188 (*Exception*). Read the three-way match. **Accept at approved hours** —
   what is the new amount?
2. **Payment run**: select every payable invoice, ACH, today → record. Which invoices were left out and why?
3. **Payroll, 1099 & referrals → W-2 payroll**: add a pay-run line for Grace Okafor. Download the payroll template.
4. **Referral fees**: how much has Kiran Patel earned and been paid? Pay the balance. Create a one-time $500 referral
   for Priya Nair, eligible in 90 days — why is *Earned* $0?
5. **1099 summary** for this year: who needs a 1099-NEC? Whose W-9 is missing?
6. **Expenses**: approve Ravi's travel expense, then mark it reimbursed.

Check: Why does a C2C vendor usually not get a 1099? *(Corporation.)* What blocks a referral payment? *(No W-9 for an individual.)*

## Session 5 — Onboarding and compliance (HR, legal)

1. **Consultants → Onboard someone** four times, one per type (W-2 full-time, W-2 contract, C2C with employer
   Orion Data Partners, 1099). Compare the checklists.
2. Tick through the W-2 contract checklist and **Finish onboarding**. Try finishing the 1099 with items open — read the message.
3. **Compliance → Work authorization & I-9**: who must be reverified first? What does the finding say for C2C?
4. **Expiring documents**: track a passport for Priya expiring in 25 days; then **Record renewal** with a date 10 years out.
5. **Policies → Publish policy** "Remote work v1" for W-2 only. Open it — who still has to accept?
6. **Registrations**: copy the public link, open it in a private window, register "Acme Talent LLC" as a vendor with a
   PDF. Back in Compliance, review the checks and **Approve**. Where did the company and its file go?
7. Offboard the 1099 contractor (reason "Project ended", rehire yes) and find them under **Former**. **Rehire** them.

Check: When must I-9 Section 2 be done? *(Within 3 business days of starting.)* Who handles I-9 for C2C? *(The vendor/employer.)*

## Session 6 — Contracts and e-signatures

1. **MSAs & SOWs → Missing & expiring**: list three gaps.
2. **Add agreement → Already signed**: record "MSA-ACME-01" with Acme Talent (you are buyer), attach a PDF on its page.
3. **Add SOW** under it: we pay, linked to client SOW *SOW-AF-0091*. Try an end date after the client SOW — read the message.
4. Open **SOW-AF-0087** → **Amend / extend**: +3 months, +$36,000 → *Send* for signature to two people (use your
   own e-mail addresses to receive the links).
5. Sign as signer 1 on your phone: code, consent, typed signature. Watch the audit trail update. Sign as signer 2
   with a drawn signature. Download the sealed PDF and find the certificate page with IP addresses.
6. Check SOW-AF-0087: new end date and value applied?

Check: What proves the signer controlled the e-mail? *(One-time code.)* What makes the PDF tamper-evident? *(SHA-256 of original and sealed PDF on the certificate and in the record.)*

## Session 7 — Administration

1. **Users & roles**: invite a viewer and a vendor user (BrightPath). Change the viewer's manager. Lock, then reactivate.
   Try to demote yourself — read the message.
2. **Import & export**: download the consultants template; add two *Former* consultants with end dates, reasons, rehire
   flags; *Check file* (introduce one bad date to see the error), fix it, *Import*. Find them under Former.
3. Export **Placements & rates**, change one rate, re-import — was it updated or duplicated?
4. **Compliance → Reminders**: change the AR overdue days to `1, 10, 20, 30`; switch policy reminders off and on.
5. **Audit log**: filter Record = placements — find your rate change and its before/after values and IP address.
6. **Workspace settings**: walk the setup checklist; review sign-in methods.

Check: What happens to a bad row during import? *(Skipped and listed; good rows are saved.)*

## Session 8 — Vendor portal

Sign in as **s.rao@brightpath.example**.
1. Read the invoices list and statuses. Why is one *Held*?
2. **Submit an invoice** for Ravi's GRC placement for last week with the approved hours. Then submit one with wrong hours — what status does it get?
3. Can you see what Northwind pays ESG? *(No — not your contract.)*

## Session 9 — Owner console

Sign in as the platform owner.
1. Read MRR, revenue per user and inactive workspaces.
2. Open the public **/signup** page in a private window and request a workspace for "Lone Star Staffing".
3. In **Sign-up requests**, open it, read the flags, **Approve & create workspace**. Find it under Workspaces — setup step 1, one invited user.
4. Extend its trial by 14 days; change plan to Enterprise.

---

## Trainer notes

- Prepare one user per role per trainee before class; use real inboxes so codes and signing links arrive.
- The seed dates are relative to today, so overdue invoices and expiring documents always look current.
- Without `RESEND_API_KEY` in staging, e-mails are logged but not sent — set it for training so codes arrive.
- Leave 10 minutes at the end of sessions 3–5 for questions about the customer's own process (pay-when-paid terms,
  approval hierarchy, who signs MSAs).

## Answer key (selected)

- S0-1 Not ESG's contract. S0-3 Admin, finance.
- S3-2 Re-running only invoices hours not already on an invoice.
- S3-6 The BrightPath pay-when-paid invoice moves from *Held* to *Ready to pay*.
- S4-1 Amount = approved hours × pay rate (64 × $82 = $5,248 in the demo data).
- S4-4 One-time fees are earned only after the eligibility date.
- S5-2 "Finish the checklist first: …" lists open items.
- S6-3 "A vendor SOW can't run past the client SOW it supports".
- S8-2 Wrong hours → *Exception*.
