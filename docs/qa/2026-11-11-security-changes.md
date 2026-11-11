# QA notes: security review changes (November 2026)

What changed in how the app behaves, which screens are affected, and how to check each item.
"Expected" is what the screen should show. **Local-tested** = checked on a local copy before going to QA.

Before testing on QA/production, the database team must apply these migrations, in this order:
1. `20261111000100_membership_company_links.sql`
2. `20261111000150_msa_accepted_by.sql`
3. `20261111000200_contract_responses_by_role.sql`
4. `20261111000300_invites_need_confirmed_email.sql`

Local test run (11 Nov 2026): all automated API tests for these changes pass, and no other test changed result.
Each section says what was also clicked through on a local copy of the app ("Local browser test").

---

## 1. Inviting a user who already has a myTrakIn login

**Changed:** if the invited e-mail already has a myTrakIn account, the admin can no longer create a password for it.
The person gets an invitation and signs in with their own password. A temporary password is only created for brand-new users.

**Affected screens:** Settings → Users → Invite user (with "Create a password login" ticked).

**How to test:**
1. As a company admin, invite an e-mail that already has a myTrakIn account, with "Create a password login" ticked.
   **Expected:** "They already have a myTrakIn login — send the invitation and they sign in with their own password". No password shown.
2. Invite a brand-new e-mail with the box ticked. **Expected:** a temporary password is shown once and e-mailed, as before.
3. The existing user's own password still works.

## 2. Wrong verification codes (e-signature and company e-mail)

**Changed:** after **5 wrong codes** the code is cancelled; even the right code is then refused and a new code must be requested.

**Affected screens:** e-signature page (code step); company registration → verify company e-mail.

**How to test:**
1. Request a code, type a wrong code 5 times. **Expected each time:** "That code isn't right. Check the latest e-mail and try again."
2. Type the right code. **Expected:** "Too many wrong codes. Ask for a new one."
3. Request a new code and type it. **Expected:** verified.

## 3. Suspended company: view only

**Changed:** users of a company suspended by myTrakIn can still sign in and look at everything, but any change
(create, edit, submit, approve, delete, upload) is refused with
**"This company is suspended. Contact the myTrakIn admin."** myTrakIn platform admins are not affected.

**Affected screens:** every screen of a suspended company; Platform console → company → Status now reads "Suspended (view only)".

**Local browser test:** PASS — suspended company still opened Compliance → Policies; publishing a policy showed the message above;
after setting the company back to Active the same publish worked.

**How to test:**
1. As myTrakIn platform admin, suspend a test company.
2. Sign in as a user of that company. **Expected:** sign-in works, lists and details open.
3. Try to save, submit a timesheet, approve, upload a file. **Expected:** the message above, nothing saved.
4. Re-activate the company. **Expected:** changes work again.

## 4. Joining by invitation needs a confirmed e-mail

**Changed:** a person invited to a workspace or company (including by bulk upload) joins it only after confirming
their e-mail address. Until then the invitation stays pending.

**Affected screens:** sign-up from an invitation; Settings → Users (status "Invited" until confirmed).

**How to test:**
1. Invite a new e-mail. Sign up with it but don't confirm the e-mail. **Expected:** no access to the workspace yet; user shows as Invited.
2. Confirm the e-mail. **Expected:** the user lands in the workspace; status becomes Active.

## 5. Company owners can only be changed by an owner

**Changed:** a company admin can no longer demote or remove an owner. Only an owner (or Super Admin / workspace admin) can.
If the first owner has left the company, the **myTrakIn admin** replaces them from the platform console after verification.

**Affected screens:** Company → Members (change role / remove); Platform console → Replace owner.

**How to test:**
1. As a company **admin** (not owner), change an owner's role or remove them.
   **Expected:** "Only an owner can change another owner" / "Only an owner can remove another owner".
2. As an owner, do the same for another owner. **Expected:** works (a company must keep at least one owner).
3. As platform admin, replace a company's owner. **Expected:** works and appears in the audit log.

## 6. Changing your password

**Changed:** Account & security → change password now needs **current password + new password + retype new password**.
The "Forgot password" e-mail link still sets a new password directly.

**How to test:**
1. Wrong current password. **Expected:** refused, password unchanged.
2. New and retyped passwords differ. **Expected:** refused.
3. Right current password, matching new ones. **Expected:** changed; signing in with the new one works.
4. Forgot-password link. **Expected:** sets a new password without the old one.
5. An account that only ever signed in with e-mail codes sets its first password through "Forgot password".

## 7. Sign-in page links and messages

**Changed:** after signing in (including after the two-step code) you only go to pages inside myTrakIn; a link pointing
elsewhere sends you to the home page. Sign-in errors use our own wording, never text from the link.

**How to test:**
1. Open `/login?next=/invoices`, sign in. **Expected:** Invoices page.
2. Open `/login?next=//example.com`, sign in. **Expected:** myTrakIn home, never another site.
3. Open `/login?error_description=Any+text+here`. **Expected:** "Sign-in didn't complete. Please try again."

**Local browser test:** PASS — `next=/invoices` opened Invoices; a link to another site (hidden with a tab character) opened the
Dashboard instead; error text from the link was replaced by our message.

## 8. Policy documents

**Changed:** a policy's name and version may contain only letters, numbers, spaces, dashes and dots
(a full naming standard will follow). Policy files must be real PDFs.

**Affected screens:** Compliance → Policies → Publish policy.

**How to test:**
1. Name "Leave Policy", version "2.0", a PDF. **Expected:** published.
2. Name with "/" or "&". **Expected:** "Policy names and versions can only use letters, numbers, spaces, dashes (-) and dots (.)"
3. A non-PDF file renamed to .pdf. **Expected:** "Policies must be PDF files".

**Note for the team:** existing policies whose names contain "&" (e.g. "Timesheet & expense policy") can't get a new
version under this rule until the naming standard is agreed (or the name is changed).

**Local browser test:** PASS — "Leave/Policy" refused with the message above; "Leave Policy" 1.0 published.

## 9. Linking users to companies and consultants

**Changed:** when an admin invites a client or vendor contact, they can link that person only to a company this workspace
works with: one of the workspace's own company records, or another workspace's company with an MSA/subcontract that the
other side really accepted. A consultant login can only be linked to this workspace's own consultant record.
Existing links that break this rule are removed (those users are deactivated and must be re-invited correctly).
A 1099 contractor invited by a vendor sees only their own timesheets, contracts and documents with that vendor.

**Affected screens:** Settings → Users → Invite user; client/vendor contact views (Invoices, Agreements, Timesheets for clients).

**How to test:**
1. Invite a vendor contact linked to one of your vendor companies. **Expected:** works; after sign-in they see only that vendor's items.
2. Invite a consultant login for one of your consultants. **Expected:** works; they see only their own timesheets/contracts/documents.
3. Check that a client contact sees only invoices, agreements and timesheets of their own company.

## 10. Recording payments

**Changed:** only **finance** and **admin** roles can record a payment or mark an invoice paid (including a client recording
its payment on a vendor invoice). Viewers, approvers, HR, consultants and outside contacts can't. Amounts on invoices another
company sent you are hidden from non-finance roles.

**Affected screens:** Invoices → Record payment / Mark paid; Payables from other companies.

**How to test:**
1. As finance, record a payment. **Expected:** works as before.
2. As a viewer / approver / consultant, open the same invoice. **Expected:** no "Record payment" button; amounts hidden where applicable.

**Local browser test:** PASS — finance recorded a payment on ESG-AR-0413 ("Payment recorded").

## 11. Timesheet approval by the end client

**Changed:** the end client's approval no longer also counts as the placing company's approval: both are needed, in order.
The end client can approve only after the placing company has approved, and only timesheets for its own placements.

**Affected screens:** Timesheets → Approve (placing company and end client); timesheet approval e-mail links.

**How to test:**
1. Consultant submits a week. End client tries to approve first. **Expected:** refused, waiting for the placing company.
2. Placing company approves, then the end client approves. **Expected:** both approvals show; week fully approved.
3. A second end client of the same consultant (different placement) can't see or approve this week.

**Local browser test:** PASS for the placing company — consultant submitted the week, admin approved it; the consultant's page shows
"Accepted — (placing company)" and "Pending — (end client)". The end client's own approval was covered by API tests only
(the local data has no end-client login).

## 12. Smaller changes

| Change | Where | Expected |
| --- | --- | --- |
| Registration confirmation e-mail uses fixed wording | Public registration form → e-mail | "We received your registration." |
| Numbering format pads the sequence to at most 10 digits | Settings → Numbering | `{SEQ:11}` or more refused with a message; `{SEQ:10}` works |
| Drawn signatures must be real images | E-signature → Draw signature | Drawing and signing works as before |
| Large file uploads (over 4 MB) | Any Attachments section | Upload works as before |
| Links into Import and Messages | `/data?entity=…`, `/network?tab=messages&with=…` | A normal link works; a broken link opens the default view |

---

## 13. Accepting MSAs, renewals and SOWs

**Changed:** only **admin, legal and account manager** roles can accept or reject an MSA, a renewal or a SOW on the company's
behalf, or request a renewal. Other roles (viewer, approver, finance, HR, consultant, vendor/client contacts) get
"Only an admin, legal or account manager can answer an MSA". Owners can still narrow this per role in Roles & permissions.

**Affected screens:** MSAs & SOWs → an MSA/SOW sent to you → Accept / Reject; Renewals.

**How to test:**
1. Send an MSA from company A to company B. As B's legal or account manager, accept. **Expected:** accepted.
2. As B's viewer or finance user, try to accept/reject. **Expected:** refused with the message above.

**Local browser test:** MSAs & SOWs list opens for admin. Accept/reject between two companies was covered by API tests only.

## 14. Who sees amounts on the Payment flow

**Changed:** consultants and other roles that don't see bill rates (HR, approver, viewer, vendor contacts) see "••••" instead of
the client's bill amounts and balances on the Payment flow and on payables from other companies. Hours are still shown.

**Local browser test:** PASS — consultant Ravi Kumar sees "168 h · C2C" and "••••" for every amount.

## 15. Import & export follow permissions

**Changed:** each user can import or export only the modules they're allowed to see (export needs view access, import needs edit
access). Placement exports blank the pay rate for account managers; company exports blank the EIN for viewer, HR, account
manager and legal. Credit notes follow the Invoices permission; document links follow the Compliance permission and no longer
open deleted documents.

**How to test:**
1. As admin, Import & export → Clients & vendors → CSV. **Expected:** downloads.
2. As an account manager, export Placements & rates. **Expected:** "AP pay rate" column empty.
3. As a viewer, export Clients & vendors. **Expected:** EIN column empty.
4. In Roles & permissions, set Invoices to "none" for a role; that role can't export invoices/payments or list credit notes.

**Local browser test:** PASS — admin export of Clients & vendors downloaded; a broken `/data?entity=` link opened the default
"Clients & vendors" import.

## 16. Adding a consultant: search by exact e-mail

**Changed:** Consultants → Onboard someone finds a person **only by their exact e-mail address**. Typing a name or part of an
e-mail shows "Type their full e-mail address — search by name isn't available." Contact details of users from other companies
are no longer listed.

**Local browser test:** PASS — "Ravi" found nobody and showed the hint; "ravi.kumar@example.com" found Ravi Kumar.

---

## Not testable on a local copy (please cover on QA)

These need the real sign-in service or two separate companies, so they were covered by API tests only:
inviting an existing user (1), e-signature / company e-mail code limit (2), joining only after e-mail confirmation (4),
owner changes and platform "Replace owner" (5), password change (6), linking contacts to another company and 1099 contractor
visibility (9), end-client approval (11), MSA acceptance between two companies (13).
