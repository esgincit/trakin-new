# myTrakIn API reference

Generated from the code by `scripts/gen-api-reference.py` — do not edit by hand.

Base URL: `https://<your-api-domain>/v1`. Every call except `/public/*`, `/health` and `/cron/*` needs
`Authorization: Bearer <Supabase access token>` and, for workspace data, `X-Tenant-Id: <workspace id>`
(optional when the person belongs to one workspace).

Errors always look like `{"error": {"code": "...", "message": "..."}}`. Common codes: `unauthorized` (401), `forbidden`,
`no_access` (403), `not_found` (404), `duplicate`, `conflict` (409), `invalid` (400/422).

In development the interactive docs are at `/docs` (Swagger) and `/redoc`. They are switched off in production.

## Contents

- [me](#me)
- [dashboard](#dashboard)
- [companies](#companies)
- [contracts](#contracts)
- [projects](#projects)
- [timesheets](#timesheets)
- [invoices](#invoices)
- [payroll, 1099 & referrals](#payroll,-1099-referrals)
- [e-signatures](#e-signatures)
- [compliance](#compliance)
- [import & export](#import-export)
- [administration](#administration)
- [network](#network)
- [smart suggestions](#smart-suggestions)
- [platform](#platform)
- [public](#public)
- [scheduled jobs](#scheduled-jobs)
- [files](#files)
- [company onboarding](#company-onboarding)
- [acceptances](#acceptances)
- [roles & permissions](#roles-permissions)
- [consultants](#consultants)
- [health](#health)

## me

### `GET /v1/me`

Profile, the workspaces this person can open, and whether they own the platform.

### `GET /v1/my/businesses`

Every business the caller created or belongs to — any role, any workspace.
Company data itself stays shielded; open a profile to see what your role allows.

### `GET /v1/session`

The caller's role in the selected workspace (drives navigation in the web app).

### `GET /v1/me/consultant`

Everything a consultant may see about themselves — no amounts, no rates.

### `POST /v1/me/policies/{policy_id}/accept`

Accept Policy

| Parameter | In | Type | Required |
|---|---|---|---|
| `policy_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `confirm` | boolean |  |

### `GET /v1/me/timesheets`

One line per week and project, newest first. Filter by project, status and dates.

| Parameter | In | Type | Required |
|---|---|---|---|
| `placement_id` | query | uuid (optional) |  |
| `status` | query | string (optional) |  |
| `from` | query | date (optional) |  |
| `to` | query | date (optional) |  |

### `GET /v1/me/expenses`

My Expenses

### `POST /v1/me/expenses`

Submit Expense

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `placement_id` | uuid (optional) |  |
| `spent_on` | date | yes |
| `category` | string | yes |
| `amount` | number or string (optional) | yes |
| `billable` | boolean |  |

### `GET /v1/me/time-off`

My Time Off

### `POST /v1/me/time-off`

Request Time Off

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `starts_on` | date | yes |
| `ends_on` | date | yes |
| `kind` | one of pto, sick, unpaid | yes |
| `note` | string (optional) |  |

### `GET /v1/me/documents/{document_id}/link`

My Document Link

| Parameter | In | Type | Required |
|---|---|---|---|
| `document_id` | path | uuid | yes |

## dashboard

### `GET /v1/dashboard`

Dashboard

## companies

### `GET /v1/companies/directory`

Searchable company directory (Business ID, name, type) for picking an agreement
counterparty: every active company in any tenant. Directory columns only — full
profiles stay gated behind tenant RLS. `exclude` drops the company the agreement
is being made from: an agreement can't be between a company and itself.

| Parameter | In | Type | Required |
|---|---|---|---|
| `q` | query | string (optional) |  |
| `exclude` | query | uuid (optional) |  |

### `GET /v1/companies`

List Companies

| Parameter | In | Type | Required |
|---|---|---|---|
| `kind` | query | string (optional) |  |
| `status` | query | string (optional) |  |

### `POST /v1/companies`

Start onboarding: any workspace member can draft a company — it gets its Business ID
and the creator becomes its owner. Activation stays staff-only through /activate.

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `name` | string | yes |
| `kind` | one of client, prime_vendor, vendor, end_client (optional) |  |
| `kinds` | list of string (optional) |  |
| `ein` | string (optional) |  |
| `state` | string (optional) |  |
| `address` | string (optional) |  |
| `contact_name` | string (optional) |  |
| `contact_email` | email (optional) |  |
| `contact_phone` | string (optional) |  |
| `default_terms` | string |  |
| `notes` | string (optional) |  |
| `domain` | string (optional) |  |
| `business_type` | string (optional) |  |
| `dba` | string (optional) |  |
| `country` | one of US, IN |  |
| `cin` | string (optional) |  |

### `GET /v1/companies/{company_id}`

Get Company

| Parameter | In | Type | Required |
|---|---|---|---|
| `company_id` | path | uuid | yes |

### `PATCH /v1/companies/{company_id}`

Update Company

| Parameter | In | Type | Required |
|---|---|---|---|
| `company_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `name` | string (optional) |  |
| `kind` | string (optional) |  |
| `kinds` | list of string (optional) |  |
| `ein` | string (optional) |  |
| `state` | string (optional) |  |
| `address` | string (optional) |  |
| `contact_name` | string (optional) |  |
| `contact_email` | email (optional) |  |
| `contact_phone` | string (optional) |  |
| `default_terms` | string (optional) |  |
| `notes` | string (optional) |  |
| `domain` | string (optional) |  |
| `business_type` | string (optional) |  |
| `dba` | string (optional) |  |
| `country` | one of US, IN (optional) |  |
| `cin` | string (optional) |  |
| `onboarding_stage` | integer (optional) |  |

### `POST /v1/companies/{company_id}/status`

Mark a client or vendor inactive (history is kept) or reactivate it.

| Parameter | In | Type | Required |
|---|---|---|---|
| `company_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `status` | one of active, inactive | yes |
| `reason` | string (optional) |  |
| `since` | date (optional) |  |

### `POST /v1/companies/{company_id}/logo`

Company logo (JPEG, PNG or WebP, up to 2 MB). Shown on the company profile.

| Parameter | In | Type | Required |
|---|---|---|---|
| `company_id` | path | uuid | yes |

Body (`multipart/form-data`):

| Field | Type | Required |
|---|---|---|
| `file` | string | yes |

### `POST /v1/companies/{company_id}/w9`

Upload a W-9: the document is stored, its fields are extracted (digital text,
otherwise OCR when available) and returned for review. Nothing is trusted until
staff verify it — the company stays non-active meanwhile.

| Parameter | In | Type | Required |
|---|---|---|---|
| `company_id` | path | uuid | yes |

Body (`multipart/form-data`):

| Field | Type | Required |
|---|---|---|
| `file` | string | yes |

### `PATCH /v1/companies/{company_id}/tax`

Correct the W-9 / tax details after reviewing the extraction. TIN is stored
digits-and-dashes only; only privileged roles ever read it back.

| Parameter | In | Type | Required |
|---|---|---|---|
| `company_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `dba` | string (optional) |  |
| `tax_classification` | string (optional) |  |
| `tin` | string (optional) |  |
| `tin_type` | one of ein, ssn (optional) |  |
| `tax_address` | string (optional) |  |
| `ein` | string (optional) |  |

### `POST /v1/companies/{company_id}/w9/decision`

Staff review the submitted W-9 against the attached document.

| Parameter | In | Type | Required |
|---|---|---|---|
| `company_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `decision` | one of verified, rejected | yes |
| `note` | string (optional) |  |

### `POST /v1/companies/{company_id}/verify`

Re-run the verification checks without activating. Shows what still blocks.

| Parameter | In | Type | Required |
|---|---|---|---|
| `company_id` | path | uuid | yes |

### `POST /v1/companies/{company_id}/activate`

Activate the company. Strict: every gate must pass — no override.

| Parameter | In | Type | Required |
|---|---|---|---|
| `company_id` | path | uuid | yes |

### `GET /v1/companies/{company_id}/members`

List Members

| Parameter | In | Type | Required |
|---|---|---|---|
| `company_id` | path | uuid | yes |

### `POST /v1/companies/{company_id}/members`

Invite someone to the company. They claim it automatically at first sign-in.

| Parameter | In | Type | Required |
|---|---|---|---|
| `company_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `email` | email | yes |
| `company_role` | one of super_admin, owner, admin, member | yes |
| `title` | string (optional) |  |

### `PATCH /v1/companies/{company_id}/members/{member_id}`

Update Member

| Parameter | In | Type | Required |
|---|---|---|---|
| `company_id` | path | uuid | yes |
| `member_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `company_role` | one of super_admin, owner, admin, member (optional) |  |
| `status` | one of active, removed (optional) |  |

### `DELETE /v1/companies/{company_id}/members/{member_id}`

Remove someone from the company (history is kept). The last owner can't be removed.

| Parameter | In | Type | Required |
|---|---|---|---|
| `company_id` | path | uuid | yes |
| `member_id` | path | uuid | yes |

### `POST /v1/companies/{company_id}/msas`

A company's owner/admin starts an MSA with another registered company —
recording one already signed, or requesting a new one. Staff can do the same.

| Parameter | In | Type | Required |
|---|---|---|---|
| `company_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `counterparty_company_id` | uuid | yes |
| `kind` | one of msa, subcontract |  |
| `tenant_side` | one of supplier, buyer |  |
| `existing` | boolean |  |
| `effective_on` | date (optional) |  |
| `expires_on` | date (optional) |  |
| `payment_terms` | string (optional) |  |
| `signed_by` | string (optional) |  |
| `note` | string (optional) |  |

## contracts

### `GET /v1/agreements`

List Agreements

| Parameter | In | Type | Required |
|---|---|---|---|
| `kind` | query | string (optional) |  |

### `POST /v1/agreements`

Add an agreement — a new draft, or one already signed outside myTrakIn (attach the PDF afterwards).

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `code` | string (optional) |  |
| `kind` | one of msa, subcontract, ica, nda, offer_letter | yes |
| `company_id` | uuid (optional) |  |
| `consultant_id` | uuid (optional) |  |
| `tenant_side` | one of supplier, buyer, employer | yes |
| `effective_on` | date | yes |
| `expires_on` | date (optional) |  |
| `payment_terms` | string (optional) |  |
| `renewal` | string (optional) |  |
| `notice_period` | string (optional) |  |
| `insurance_required` | string (optional) |  |
| `status` | one of draft, active |  |
| `signed_by` | string (optional) |  |
| `source` | one of myTrakIn, manual, imported |  |

### `POST /v1/agreements/{agreement_id}/respond`

The company an MSA was sent to accepts it (it comes into force) or rejects it with a note.

| Parameter | In | Type | Required |
|---|---|---|---|
| `agreement_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `decision` | one of accept, reject | yes |
| `note` | string (optional) |  |

### `POST /v1/agreements/{agreement_id}/renewals`

Either company asks to renew an MSA until a new end date. The other company accepts or declines.

| Parameter | In | Type | Required |
|---|---|---|---|
| `agreement_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `expires_on` | date | yes |
| `note` | string (optional) |  |

### `POST /v1/agreements/renewals/{renewal_id}/respond`

Accept a renewal (the end date moves to the one proposed) or decline it with a note.

| Parameter | In | Type | Required |
|---|---|---|---|
| `renewal_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `decision` | one of accept, decline | yes |
| `note` | string (optional) |  |

### `GET /v1/agreements/{agreement_id}`

Get Agreement

| Parameter | In | Type | Required |
|---|---|---|---|
| `agreement_id` | path | uuid | yes |

### `GET /v1/sows`

List Sows

| Parameter | In | Type | Required |
|---|---|---|---|
| `side` | query | string (optional) |  |

### `POST /v1/sows`

Add a SOW / work order — new, or already signed outside myTrakIn with what was invoiced before.

The agreement may be one this workspace recorded or one another workspace recorded
with one of our companies: work under an MSA runs both ways.

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `code` | string (optional) |  |
| `agreement_id` | uuid | yes |
| `project_id` | uuid (optional) |  |
| `side` | one of we_bill, we_pay | yes |
| `title` | string | yes |
| `start_date` | date | yes |
| `end_date` | date | yes |
| `value_cap` | number or string (optional) |  |
| `prior_invoiced` | number or string (optional) |  |
| `prior_paid` | number or string (optional) |  |
| `flows_from_sow_id` | uuid (optional) |  |
| `status` | one of draft, active |  |

### `POST /v1/projects/{project_id}/sows`

Add a SOW (or a vendor / contractor work order) under a project (WF-04).

| Parameter | In | Type | Required |
|---|---|---|---|
| `project_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `code` | string (optional) |  |
| `agreement_id` | uuid | yes |
| `project_id` | uuid (optional) |  |
| `side` | one of we_bill, we_pay | yes |
| `title` | string | yes |
| `start_date` | date | yes |
| `end_date` | date | yes |
| `value_cap` | number or string (optional) |  |
| `prior_invoiced` | number or string (optional) |  |
| `prior_paid` | number or string (optional) |  |
| `flows_from_sow_id` | uuid (optional) |  |
| `status` | one of draft, active |  |

### `GET /v1/sows/{sow_id}`

Get Sow

| Parameter | In | Type | Required |
|---|---|---|---|
| `sow_id` | path | uuid | yes |

### `POST /v1/sows/{sow_id}/submit`

Send a draft SOW to the other company for approval. Until this is done it is a
draft and the other company cannot see it.

| Parameter | In | Type | Required |
|---|---|---|---|
| `sow_id` | path | uuid | yes |

### `POST /v1/sows/{sow_id}/respond`

The company a SOW was sent to approves it (it comes into force) or turns it down
with a reason.

| Parameter | In | Type | Required |
|---|---|---|---|
| `sow_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `decision` | one of approve, reject | yes |
| `note` | string (optional) |  |

### `POST /v1/sows/{sow_id}/amendments`

Add Amendment

| Parameter | In | Type | Required |
|---|---|---|---|
| `sow_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `summary` | string | yes |
| `new_end_date` | date (optional) |  |
| `value_change` | number or string (optional) |  |

### `GET /v1/contracts/missing`

What is missing or expiring: agreements, NDAs, offers, policies, documents.

## projects

### `GET /v1/projects/next-code`

Suggested code for the New project form, from the tenant's numbering template (the field stays editable).

| Parameter | In | Type | Required |
|---|---|---|---|
| `client_company_id` | query | uuid (optional) |  |

### `GET /v1/projects`

List Projects

### `POST /v1/projects`

Create Project

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `code` | string (optional) |  |
| `name` | string | yes |
| `client_company_id` | uuid (optional) |  |
| `prime_company_id` | uuid (optional) |  |
| `description` | string (optional) |  |
| `start_date` | date (optional) |  |
| `end_date` | date (optional) |  |
| `client_approver` | string (optional) |  |
| `status` | one of planned, active, completed, internal |  |

### `GET /v1/projects/{project_id}`

Get Project

| Parameter | In | Type | Required |
|---|---|---|---|
| `project_id` | path | uuid | yes |

### `PATCH /v1/projects/{project_id}`

Update Project

| Parameter | In | Type | Required |
|---|---|---|---|
| `project_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `code` | string (optional) |  |
| `name` | string | yes |
| `client_company_id` | uuid (optional) |  |
| `prime_company_id` | uuid (optional) |  |
| `description` | string (optional) |  |
| `start_date` | date (optional) |  |
| `end_date` | date (optional) |  |
| `client_approver` | string (optional) |  |
| `status` | one of planned, active, completed, internal |  |

### `GET /v1/placements`

List Placements

| Parameter | In | Type | Required |
|---|---|---|---|
| `status` | query | string (optional) |  |
| `project_id` | query | uuid (optional) |  |

### `POST /v1/placements`

Create Placement

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `consultant_id` | uuid | yes |
| `project_id` | uuid | yes |
| `role_title` | string (optional) |  |
| `start_date` | date | yes |
| `end_date` | date (optional) |  |
| `hours_per_week` | number or string (optional) |  |
| `end_client_company_id` | uuid (optional) |  |
| `ar_company_id` | uuid (optional) |  |
| `ar_sow_id` | uuid (optional) |  |
| `bill_rate` | number or string (optional) |  |
| `ar_terms` | string (optional) |  |
| `ap_company_id` | uuid (optional) |  |
| `ap_consultant_id` | uuid (optional) |  |
| `ap_sow_id` | uuid (optional) |  |
| `pay_rate` | number or string (optional) |  |
| `ap_terms` | string (optional) |  |
| `pay_when_paid` | boolean |  |

### `GET /v1/sows/{sow_id}/resources`

Everyone working under this SOW or work order — each with their own contract, timesheets, invoices and payments.

| Parameter | In | Type | Required |
|---|---|---|---|
| `sow_id` | path | uuid | yes |

### `POST /v1/sows/{sow_id}/resources`

Put a consultant on a SOW: one SOW can carry one or many resources (WF-04).

| Parameter | In | Type | Required |
|---|---|---|---|
| `sow_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `consultant_id` | uuid | yes |
| `project_id` | uuid (optional) |  |
| `role_title` | string (optional) |  |
| `start_date` | date | yes |
| `end_date` | date (optional) |  |
| `hours_per_week` | number or string (optional) |  |
| `end_client_company_id` | uuid (optional) |  |
| `ar_company_id` | uuid (optional) |  |
| `ar_sow_id` | uuid (optional) |  |
| `bill_rate` | number or string (optional) |  |
| `ar_terms` | string (optional) |  |
| `ap_company_id` | uuid (optional) |  |
| `ap_consultant_id` | uuid (optional) |  |
| `ap_sow_id` | uuid (optional) |  |
| `pay_rate` | number or string (optional) |  |
| `ap_terms` | string (optional) |  |
| `pay_when_paid` | boolean |  |

### `PATCH /v1/placements/{placement_id}`

Change dates, hours, status or rates. Rate changes apply to time not yet invoiced and are audited.

| Parameter | In | Type | Required |
|---|---|---|---|
| `placement_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `role_title` | string (optional) |  |
| `end_date` | date (optional) |  |
| `hours_per_week` | number or string (optional) |  |
| `status` | one of onboarding, active, ending, completed, ended (optional) |  |
| `bill_rate` | number or string (optional) |  |
| `pay_rate` | number or string (optional) |  |
| `ar_terms` | string (optional) |  |
| `ap_terms` | string (optional) |  |
| `pay_when_paid` | boolean (optional) |  |

## timesheets

### `GET /v1/timesheets`

Every consultant with work that week: hours per day, status and the result of the checks.

| Parameter | In | Type | Required |
|---|---|---|---|
| `week` | query | date (optional) |  |

### `GET /v1/timesheets/history`

All weeks, one line per consultant, week and project.

| Parameter | In | Type | Required |
|---|---|---|---|
| `consultant_id` | query | uuid (optional) |  |
| `from` | query | date (optional) |  |
| `to` | query | date (optional) |  |

### `GET /v1/timesheets/mine`

My Week

| Parameter | In | Type | Required |
|---|---|---|---|
| `week` | query | date (optional) |  |

### `PUT /v1/timesheets/mine`

Save My Week

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `week_start` | date | yes |
| `rows` | list of Row | yes |
| `note` | string (optional) |  |

### `POST /v1/timesheets/mine/submit`

Submit My Week

| Parameter | In | Type | Required |
|---|---|---|---|
| `week` | query | date | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `reason` | string (optional) |  |

### `GET /v1/timesheets/{timesheet_id}`

Review

| Parameter | In | Type | Required |
|---|---|---|---|
| `timesheet_id` | path | uuid | yes |

### `POST /v1/timesheets/{timesheet_id}/approve`

Approve

| Parameter | In | Type | Required |
|---|---|---|---|
| `timesheet_id` | path | uuid | yes |

### `POST /v1/timesheets/{timesheet_id}/reject`

Reject

| Parameter | In | Type | Required |
|---|---|---|---|
| `timesheet_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `reason` | string (optional) |  |

### `POST /v1/timesheets/approve-passing`

Approve every submitted timesheet for the week whose checks all pass.

| Parameter | In | Type | Required |
|---|---|---|---|
| `week` | query | date | yes |

## invoices

### `GET /v1/invoices`

List Invoices

| Parameter | In | Type | Required |
|---|---|---|---|
| `direction` | query | one of ar, ap | yes |
| `status` | query | string (optional) |  |

### `POST /v1/invoices`

Create a client invoice by hand. Rate comes from the placement, terms from its AR settings.

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `placement_id` | uuid | yes |
| `period_start` | date | yes |
| `period_end` | date | yes |
| `hours` | number or string (optional) | yes |
| `po_number` | string (optional) |  |
| `memo` | string (optional) |  |
| `send` | boolean |  |

### `GET /v1/invoices/{invoice_id}`

Get Invoice

| Parameter | In | Type | Required |
|---|---|---|---|
| `invoice_id` | path | uuid | yes |

### `POST /v1/invoices/generate`

Create draft AR invoices (and matching AP payables) from approved timesheets.

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `period_start` | date | yes |
| `period_end` | date | yes |
| `issue_on` | date (optional) |  |

### `POST /v1/invoices/{invoice_id}/send`

Send a draft client invoice: it is dated today and e-mailed to the customer's contact.

| Parameter | In | Type | Required |
|---|---|---|---|
| `invoice_id` | path | uuid | yes |

### `POST /v1/vendor-invoices`

A vendor submits its invoice. It is matched against approved timesheets automatically.

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `number` | string | yes |
| `placement_id` | uuid | yes |
| `period_start` | date | yes |
| `period_end` | date | yes |
| `hours` | number or string (optional) | yes |

### `POST /v1/invoices/{invoice_id}/payments`

Record money received from a customer or paid to a vendor. Paying an AR invoice in full
releases any pay-when-paid vendor invoices waiting on it.

| Parameter | In | Type | Required |
|---|---|---|---|
| `invoice_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `amount` | number or string (optional) | yes |
| `paid_on` | date | yes |
| `method` | one of ACH, Wire, Check, Card, Other | yes |
| `reference` | string (optional) |  |
| `status` | one of pending, processing, completed |  |

### `POST /v1/payments/{payment_id}/status`

Move a payment in flight forward: pending → processing → completed. Completed counts against the invoice.

| Parameter | In | Type | Required |
|---|---|---|---|
| `payment_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `status` | one of processing, completed | yes |

### `POST /v1/payments/{payment_id}/confirm`

Payment confirmation closes the financial lifecycle: finance confirms money received from a customer;
the vendor (or 1099 contractor) — or finance on their behalf — confirms money paid to them.

| Parameter | In | Type | Required |
|---|---|---|---|
| `payment_id` | path | uuid | yes |

### `POST /v1/invoices/{invoice_id}/notes`

Add Note

| Parameter | In | Type | Required |
|---|---|---|---|
| `invoice_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `body` | string | yes |

### `POST /v1/invoices/{invoice_id}/resolve`

Accept a vendor invoice at the approved hours (amount is recalculated).

| Parameter | In | Type | Required |
|---|---|---|---|
| `invoice_id` | path | uuid | yes |

### `POST /v1/invoices/{invoice_id}/void`

Void Invoice

| Parameter | In | Type | Required |
|---|---|---|---|
| `invoice_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `body` | string | yes |

### `POST /v1/invoices/{invoice_id}/credit-notes`

Credit part or all of a client invoice's open balance. Credits count like payments: the balance and aging
drop at once, and a client invoice settled by credit releases the pay-when-paid vendor invoices waiting on it.

| Parameter | In | Type | Required |
|---|---|---|---|
| `invoice_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `amount` | number or string (optional) | yes |
| `reason` | string | yes |

### `GET /v1/credit-notes`

Every credit note with its invoice and customer. Open = the invoice still has a balance; applied = settled.

### `POST /v1/payment-runs`

Pay several vendor / 1099 invoices at once. Held or mismatched invoices are skipped.

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `invoice_ids` | list of uuid | yes |
| `method` | one of ACH, Wire, Check |  |
| `paid_on` | date (optional) |  |

### `GET /v1/payments`

Every payment in and out, newest first.

| Parameter | In | Type | Required |
|---|---|---|---|
| `from` | query | date (optional) |  |

### `GET /v1/payment-flow`

One row per placement and period: the AR card and the AP card side by side.

| Parameter | In | Type | Required |
|---|---|---|---|
| `only_open` | query | boolean |  |

## payroll, 1099 & referrals

### `GET /v1/payroll`

Payroll

| Parameter | In | Type | Required |
|---|---|---|---|
| `from` | query | date (optional) |  |
| `to` | query | date (optional) |  |

### `POST /v1/payroll`

Add Payroll

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `consultant_id` | uuid | yes |
| `period_start` | date | yes |
| `period_end` | date | yes |
| `pay_date` | date | yes |
| `hours` | number or string (optional) |  |
| `gross` | number or string (optional) | yes |
| `employer_taxes` | number or string (optional) |  |
| `benefits` | number or string (optional) |  |
| `net` | number or string (optional) |  |

### `GET /v1/payroll/margin`

Billed (AR) versus fully loaded payroll cost per W-2 employee for a period.

| Parameter | In | Type | Required |
|---|---|---|---|
| `from` | query | date | yes |
| `to` | query | date | yes |

### `GET /v1/referrals`

Referrals

### `POST /v1/referrals`

Add Referral

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `referrer_name` | string | yes |
| `referrer_type` | one of individual_1099, company, employee | yes |
| `consultant_id` | uuid | yes |
| `basis` | one of hourly, one_time | yes |
| `rate_per_hour` | number or string (optional) |  |
| `hour_cap` | number or string (optional) |  |
| `one_time_amount` | number or string (optional) |  |
| `eligible_on` | date (optional) |  |
| `w9_on_file` | boolean |  |

### `POST /v1/referrals/{agreement_id}/payments`

Pay Referral

| Parameter | In | Type | Required |
|---|---|---|---|
| `agreement_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `amount` | number or string (optional) | yes |
| `paid_on` | date | yes |
| `reference` | string (optional) |  |

### `PATCH /v1/referrals/{agreement_id}`

Update Referral

| Parameter | In | Type | Required |
|---|---|---|---|
| `agreement_id` | path | uuid | yes |
| `w9_on_file` | query | boolean | yes |

### `GET /v1/form-1099`

Everything paid to 1099 contractors and individual referrers in a calendar year (cash basis).

| Parameter | In | Type | Required |
|---|---|---|---|
| `year` | query | integer | yes |
| `threshold` | query | number or string (optional) |  |

### `GET /v1/expenses`

Expenses

| Parameter | In | Type | Required |
|---|---|---|---|
| `status` | query | string (optional) |  |

### `POST /v1/expenses/{expense_id}/decision`

Decide Expense

| Parameter | In | Type | Required |
|---|---|---|---|
| `expense_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `decision` | string | yes |
| `note` | string (optional) |  |

### `GET /v1/time-off`

Time Off

| Parameter | In | Type | Required |
|---|---|---|---|
| `status` | query | string (optional) |  |

### `POST /v1/time-off/{request_id}/decision`

Decide Time Off

| Parameter | In | Type | Required |
|---|---|---|---|
| `request_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `decision` | string | yes |
| `note` | string (optional) |  |

## e-signatures

### `GET /v1/envelopes/signing-parties`

Who is expected to sign: us (the person sending, from their own company) and the
people who may sign for the other company. The counterparty's admins are offered as a
pick list rather than typed in — a document can only ask the company's own admins to
sign for it. Their company record itself stays unreadable (RULE-01).

| Parameter | In | Type | Required |
|---|---|---|---|
| `agreement_id` | query | uuid (optional) |  |
| `sow_id` | query | uuid (optional) |  |
| `amendment_id` | query | uuid (optional) |  |

### `GET /v1/envelopes`

List Envelopes

| Parameter | In | Type | Required |
|---|---|---|---|
| `status` | query | string (optional) |  |

### `POST /v1/envelopes`

Prepare an envelope (draft). Nothing is sent until you call /send.

Body (`multipart/form-data`):

| Field | Type | Required |
|---|---|---|
| `title` | string | yes |
| `signers` | string | yes |
| `message` | string (optional) |  |
| `agreement_id` | uuid (optional) |  |
| `sow_id` | uuid (optional) |  |
| `amendment_id` | uuid (optional) |  |
| `consultant_id` | uuid (optional) |  |
| `sequential` | boolean |  |
| `remind_every_days` | integer |  |
| `files` | list of string (optional) |  |
| `document_paths` | string (optional) |  |
| `file` | string (optional) |  |
| `document_path` | string (optional) |  |

### `GET /v1/envelopes/{envelope_id}`

Get Envelope

| Parameter | In | Type | Required |
|---|---|---|---|
| `envelope_id` | path | uuid | yes |

### `GET /v1/envelopes/{envelope_id}/documents/{document_id}/download`

A link to one document of the envelope, so it can be read without signing anything.

| Parameter | In | Type | Required |
|---|---|---|---|
| `envelope_id` | path | uuid | yes |
| `document_id` | path | uuid | yes |

### `POST /v1/envelopes/{envelope_id}/documents`

Add one more PDF to a draft envelope (an exhibit, a SOW under the MSA).

| Parameter | In | Type | Required |
|---|---|---|---|
| `envelope_id` | path | uuid | yes |

Body (`multipart/form-data`):

| Field | Type | Required |
|---|---|---|
| `file` | string (optional) |  |
| `document_path` | string (optional) |  |

### `DELETE /v1/envelopes/{envelope_id}/documents/{document_id}`

Take a document out of a draft envelope and renumber what is left.

| Parameter | In | Type | Required |
|---|---|---|---|
| `envelope_id` | path | uuid | yes |
| `document_id` | path | uuid | yes |

### `POST /v1/envelopes/{envelope_id}/send`

Send to the first signer (sequential) or to everyone (parallel).

| Parameter | In | Type | Required |
|---|---|---|---|
| `envelope_id` | path | uuid | yes |

### `POST /v1/envelopes/{envelope_id}/remind`

Send a fresh link to whoever the envelope is waiting on.

| Parameter | In | Type | Required |
|---|---|---|---|
| `envelope_id` | path | uuid | yes |

### `POST /v1/envelopes/{envelope_id}/void`

Void

| Parameter | In | Type | Required |
|---|---|---|---|
| `envelope_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `reason` | string | yes |

### `GET /v1/envelopes/{envelope_id}/download`

A 5-minute link to the sealed PDF (with certificate) or, before completion, the original.

| Parameter | In | Type | Required |
|---|---|---|---|
| `envelope_id` | path | uuid | yes |

## compliance

### `GET /v1/compliance/documents`

Everything that expires, soonest first, with how many days are left.

| Parameter | In | Type | Required |
|---|---|---|---|
| `within_days` | query | integer (optional) |  |

### `POST /v1/compliance/documents`

Add Tracked

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `consultant_id` | uuid (optional) |  |
| `company_id` | uuid (optional) |  |
| `doc_type` | one of i9_reverification, passport, ead, i94, visa_notice, coi, w9, background_check, certification, drivers_license, agreement, other | yes |
| `label` | string | yes |
| `expires_on` | date (optional) |  |
| `status` | one of valid, missing, pending, expired, renewed |  |
| `blocks` | string (optional) |  |
| `recipients` | list of string |  |

### `POST /v1/compliance/documents/{doc_id}/renew`

A new document arrived: record the new expiry date. Reminders restart from it.

| Parameter | In | Type | Required |
|---|---|---|---|
| `doc_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `expires_on` | date | yes |
| `note` | string (optional) |  |

### `DELETE /v1/compliance/documents/{doc_id}`

Stop Tracking

| Parameter | In | Type | Required |
|---|---|---|---|
| `doc_id` | path | uuid | yes |

### `GET /v1/compliance/work-authorization`

I-9 / E-Verify / work-authorization status for everyone who is not former.

### `GET /v1/policies`

List Policies

### `POST /v1/policies`

Publish a policy (or a new version). Older versions of the same policy are retired.

Body (`multipart/form-data`):

| Field | Type | Required |
|---|---|---|
| `name` | string | yes |
| `version` | string | yes |
| `effective_on` | date | yes |
| `applies_to` | string |  |
| `file` | string (optional) |  |

### `GET /v1/policies/{policy_id}/acceptances`

Who accepted (with time and IP address) and who still needs to.

| Parameter | In | Type | Required |
|---|---|---|---|
| `policy_id` | path | uuid | yes |

### `GET /v1/policies/{policy_id}/file`

Policy File

| Parameter | In | Type | Required |
|---|---|---|---|
| `policy_id` | path | uuid | yes |

### `GET /v1/registrations`

Registrations

| Parameter | In | Type | Required |
|---|---|---|---|
| `status` | query | string (optional) |  |

### `GET /v1/registrations/{reg_id}`

Registration

| Parameter | In | Type | Required |
|---|---|---|---|
| `reg_id` | path | uuid | yes |

### `POST /v1/registrations/{reg_id}/decision`

Approve (creates the company or the consultant, starting onboarding), reject, or ask for more information.

| Parameter | In | Type | Required |
|---|---|---|---|
| `reg_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `decision` | one of approved, rejected, needs_info | yes |
| `note` | string (optional) |  |

### `GET /v1/files`

List Files

| Parameter | In | Type | Required |
|---|---|---|---|
| `owner_type` | query | string | yes |
| `owner_id` | query | uuid | yes |

### `POST /v1/files`

Attach a file up to 4 MB to a company, consultant, project, contract or invoice.
Larger files (up to 25 MB): POST /uploads, PUT the file, then POST /files/confirm.

Body (`multipart/form-data`):

| Field | Type | Required |
|---|---|---|
| `owner_type` | one of company, consultant, project, agreement, sow, invoice, policy, expense | yes |
| `owner_id` | uuid | yes |
| `file` | string | yes |

### `POST /v1/files/confirm`

Record a file the browser uploaded straight to storage (see /uploads).

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `owner_type` | one of company, consultant, project, agreement, sow, invoice, policy, expense | yes |
| `owner_id` | uuid | yes |
| `path` | string | yes |
| `name` | string | yes |
| `content_type` | string (optional) |  |

### `GET /v1/files/{file_id}/link`

File Link

| Parameter | In | Type | Required |
|---|---|---|---|
| `file_id` | path | uuid | yes |

### `DELETE /v1/files/{file_id}`

Soft delete: hidden at once, purged after 30 days, and the removal is in the audit log.

| Parameter | In | Type | Required |
|---|---|---|---|
| `file_id` | path | uuid | yes |

### `GET /v1/reminder-rules`

Reminder Rules

### `PATCH /v1/reminder-rules/{rule_id}`

Update Rule

| Parameter | In | Type | Required |
|---|---|---|---|
| `rule_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `offsets` | list of integer (optional) |  |
| `channels` | list of string (optional) |  |
| `enabled` | boolean (optional) |  |

### `GET /v1/notifications`

Notification Log

| Parameter | In | Type | Required |
|---|---|---|---|
| `kind` | query | string (optional) |  |
| `limit` | query | integer |  |

## import & export

### `GET /v1/data/templates`

Templates

### `GET /v1/data/templates/{key}.csv`

Template Csv

| Parameter | In | Type | Required |
|---|---|---|---|
| `key` | path | string | yes |

### `POST /v1/data/import/{key}`

Import Csv

| Parameter | In | Type | Required |
|---|---|---|---|
| `key` | path | string | yes |
| `dry_run` | query | boolean |  |

Body (`multipart/form-data`):

| Field | Type | Required |
|---|---|---|
| `file` | string | yes |

### `GET /v1/data/import-jobs`

Import Jobs

### `GET /v1/data/export/{key}.csv`

Export Csv

| Parameter | In | Type | Required |
|---|---|---|---|
| `key` | path | string | yes |

## administration

### `GET /v1/users`

List Users

### `POST /v1/users`

Invite someone. They sign in with this e-mail (code, SSO or password) and land in this workspace.

With create_login, their password login is made right away (confirmed, no e-mail
needed) and the temporary password is e-mailed to them plus returned once here.

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `email` | email | yes |
| `role` | one of tenant_admin, finance, account_manager, legal, hr, approver, viewer, vendor_admin, client_user, consultant | yes |
| `title` | string (optional) |  |
| `company_id` | uuid (optional) |  |
| `consultant_id` | uuid (optional) |  |
| `manager_id` | uuid (optional) |  |
| `signing_limit` | number or string (optional) |  |
| `create_login` | boolean |  |

### `PATCH /v1/users/{membership_id}`

Update User

| Parameter | In | Type | Required |
|---|---|---|---|
| `membership_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `role` | one of tenant_admin, finance, account_manager, legal, hr, approver, viewer, vendor_admin, client_user, consultant (optional) |  |
| `title` | string (optional) |  |
| `manager_id` | uuid (optional) |  |
| `signing_limit` | number or string (optional) |  |
| `status` | one of active, locked, deactivated (optional) |  |
| `mfa_allowed` | boolean (optional) |  |

### `DELETE /v1/users/{membership_id}`

Withdraw an invitation that hasn't been accepted. Active users are deactivated instead (history is kept).

| Parameter | In | Type | Required |
|---|---|---|---|
| `membership_id` | path | uuid | yes |

### `POST /v1/users/{membership_id}/transfer-ownership`

Hand the company to another staff user. They become admin + owner; you stay an admin.

| Parameter | In | Type | Required |
|---|---|---|---|
| `membership_id` | path | uuid | yes |

### `GET /v1/audit`

Who changed what, when, and from which IP address. Newest first; page with `before_id`.

| Parameter | In | Type | Required |
|---|---|---|---|
| `entity` | query | string (optional) |  |
| `entity_id` | query | string (optional) |  |
| `actor` | query | uuid (optional) |  |
| `action` | query | one of insert, update, delete (optional) |  |
| `since` | query | date (optional) |  |
| `until` | query | date (optional) |  |
| `q` | query | string (optional) |  |
| `limit` | query | integer |  |
| `before_id` | query | integer (optional) |  |

### `GET /v1/workspace`

Workspace

### `PATCH /v1/workspace`

Update Workspace

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `name` | string (optional) |  |
| `legal_name` | string (optional) |  |
| `ein` | string (optional) |  |
| `state` | string (optional) |  |
| `settings` | object (optional) |  |

### `GET /v1/workspace/workflow`

The workflow switches every gate reads (NDA, MSA, acceptance, resource contract).

### `GET /v1/workspace/numbering`

Numbering template per entity (saved or default) with the next number each would produce (WF-08).

### `POST /v1/workspace/onboarding-step`

The admin moved through the setup checklist. Step 8 = live.

| Parameter | In | Type | Required |
|---|---|---|---|
| `step` | query | integer | yes |

## network

### `GET /v1/network/me`

My Profile

### `PATCH /v1/network/me`

Update Profile

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `full_name` | string (optional) |  |
| `headline` | string (optional) |  |
| `location` | string (optional) |  |
| `about` | string (optional) |  |
| `phone` | string (optional) |  |
| `website` | string (optional) |  |
| `open_to_work` | boolean (optional) |  |
| `visibility` | one of network, company_and_connections, company (optional) |  |
| `show_contact` | boolean (optional) |  |
| `skills` | list of string (optional) |  |
| `experience` | list of ExperienceItem (optional) |  |
| `certifications` | list of CertificationItem (optional) |  |
| `education` | list of EducationItem (optional) |  |
| `preferences` | object (optional) |  |
| `notifications` | object (optional) |  |

### `POST /v1/network/me/photo`

Profile photo or cover image (JPEG, PNG or WebP, up to 4 MB).

| Parameter | In | Type | Required |
|---|---|---|---|
| `kind` | query | one of avatar, cover |  |

Body (`multipart/form-data`):

| Field | Type | Required |
|---|---|---|
| `file` | string | yes |

### `DELETE /v1/network/me/photo`

Remove Photo

| Parameter | In | Type | Required |
|---|---|---|---|
| `kind` | query | one of avatar, cover |  |

### `GET /v1/network/people`

Search people by name, headline, skill or location.

| Parameter | In | Type | Required |
|---|---|---|---|
| `q` | query | string (optional) |  |
| `open_to_work` | query | boolean (optional) |  |
| `limit` | query | integer |  |

### `GET /v1/network/people/{person_id}`

Person

| Parameter | In | Type | Required |
|---|---|---|---|
| `person_id` | path | uuid | yes |

### `GET /v1/network/connections`

Connections

### `POST /v1/network/connections/{person_id}`

Connect

| Parameter | In | Type | Required |
|---|---|---|---|
| `person_id` | path | uuid | yes |

### `DELETE /v1/network/connections/{person_id}`

Disconnect

| Parameter | In | Type | Required |
|---|---|---|---|
| `person_id` | path | uuid | yes |

### `POST /v1/network/connections/{person_id}/respond`

Respond

| Parameter | In | Type | Required |
|---|---|---|---|
| `person_id` | path | uuid | yes |
| `accept` | query | boolean | yes |

### `GET /v1/network/feed`

Posts from this workspace plus network-wide posts from people you can see. Newest first.

| Parameter | In | Type | Required |
|---|---|---|---|
| `before` | query | string (optional) |  |
| `limit` | query | integer |  |

### `POST /v1/network/posts`

Post

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `body` | string | yes |
| `kind` | one of update, kudos, announcement, opening |  |
| `audience` | one of company, network |  |

### `POST /v1/network/posts/{post_id}/like`

Like

| Parameter | In | Type | Required |
|---|---|---|---|
| `post_id` | path | uuid | yes |

### `DELETE /v1/network/posts/{post_id}`

Delete Post

| Parameter | In | Type | Required |
|---|---|---|---|
| `post_id` | path | uuid | yes |

### `GET /v1/network/messages`

One row per conversation with the latest message and unread count.

### `GET /v1/network/messages/{person_id}`

Conversation

| Parameter | In | Type | Required |
|---|---|---|---|
| `person_id` | path | uuid | yes |
| `limit` | query | integer |  |

### `POST /v1/network/messages/{person_id}`

Message anyone whose profile you can see (colleagues, connections, consultants at other companies).

| Parameter | In | Type | Required |
|---|---|---|---|
| `person_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `body` | string | yes |

## smart suggestions

### `GET /v1/insights`

Suggestions

### `POST /v1/insights/ask`

Plain-English answer grounded only in the caller's own suggestions list.

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `question` | string | yes |

## platform

### `GET /v1/platform/metrics`

Everything on the platform dashboard: people, companies, the onboarding pipeline, our SaaS revenue
and the money moving through myTrakIn (totals only).

### `GET /v1/platform/tenants`

Tenants

### `PATCH /v1/platform/tenants/{tenant_id}`

Change plan, extend a trial, suspend (users can't sign in) or close a company.

| Parameter | In | Type | Required |
|---|---|---|---|
| `tenant_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `plan` | one of starter, growth, enterprise (optional) |  |
| `status` | one of onboarding, active, suspended, closed (optional) |  |
| `trial_ends_on` | date (optional) |  |

### `GET /v1/platform/companies`

Every company on myTrakIn. status=pending -> registered and waiting for activation.

| Parameter | In | Type | Required |
|---|---|---|---|
| `status` | query | string (optional) |  |

### `GET /v1/platform/companies/{tenant_id}`

What the platform needs to decide: the company's onboarding record, W-9 and verification checks.

| Parameter | In | Type | Required |
|---|---|---|---|
| `tenant_id` | path | uuid | yes |

### `POST /v1/platform/companies/{tenant_id}/decision`

Activate a new company, ask its owner for more, or reject it (closed). The owner is e-mailed.

| Parameter | In | Type | Required |
|---|---|---|---|
| `tenant_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `decision` | one of activate, needs_info, reject | yes |
| `note` | string (optional) |  |

### `POST /v1/platform/companies/{tenant_id}/owner`

Support action when an owner has left: make an existing active staff user the owner (audited).

| Parameter | In | Type | Required |
|---|---|---|---|
| `tenant_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `email` | email | yes |

### `GET /v1/platform/admins`

Admins

### `POST /v1/platform/admins`

Add Admin

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `email` | email | yes |

### `DELETE /v1/platform/admins/{user_id}`

Remove Admin

| Parameter | In | Type | Required |
|---|---|---|---|
| `user_id` | path | uuid | yes |

## public

### `GET /v1/public/sign/{token}`

View

| Parameter | In | Type | Required |
|---|---|---|---|
| `token` | path | string | yes |

### `POST /v1/public/sign/{token}/code`

E-mail a 6-digit code to the signer's address (proves they control it).

| Parameter | In | Type | Required |
|---|---|---|---|
| `token` | path | string | yes |

### `POST /v1/public/sign/{token}/verify`

Verify

| Parameter | In | Type | Required |
|---|---|---|---|
| `token` | path | string | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `code` | string | yes |

### `POST /v1/public/sign/{token}/consent`

The signer agrees to do business electronically (ESIGN Act § 101(c)).

| Parameter | In | Type | Required |
|---|---|---|---|
| `token` | path | string | yes |

### `GET /v1/public/sign/{token}/document`

The PDF to review. Opens only after the e-mail code is verified.

| Parameter | In | Type | Required |
|---|---|---|---|
| `token` | path | string | yes |

### `POST /v1/public/sign/{token}/sign`

Sign

| Parameter | In | Type | Required |
|---|---|---|---|
| `token` | path | string | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `signature_type` | one of typed, drawn | yes |
| `signature_data` | string | yes |
| `agree` | boolean | yes |

### `POST /v1/public/sign/{token}/decline`

Decline

| Parameter | In | Type | Required |
|---|---|---|---|
| `token` | path | string | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `reason` | string | yes |

### `GET /v1/public/workspaces/{tenant_id}`

Name of the company whose registration page this is.

| Parameter | In | Type | Required |
|---|---|---|---|
| `tenant_id` | path | uuid | yes |

### `POST /v1/public/workspaces/{tenant_id}/registrations`

A vendor, client or contractor registers. Staff review and approve it in Compliance.

| Parameter | In | Type | Required |
|---|---|---|---|
| `tenant_id` | path | uuid | yes |

Body (`multipart/form-data`):

| Field | Type | Required |
|---|---|---|
| `kind` | one of client, vendor, 1099, consultant | yes |
| `name` | string | yes |
| `contact` | string | yes |
| `email` | email | yes |
| `phone` | string (optional) |  |
| `state` | string (optional) |  |
| `ein` | string (optional) |  |
| `files` | list of string (optional) |  |

## scheduled jobs

### `GET /v1/cron/daily`

Daily

## files

### `POST /v1/uploads`

Start Upload

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `purpose` | string | yes |
| `filename` | string | yes |
| `content_type` | string | yes |
| `size` | integer | yes |
| `owner_type` | one of company, consultant, project, agreement, sow, invoice, policy, expense (optional) |  |
| `owner_id` | uuid (optional) |  |

## company onboarding

### `GET /v1/onboarding/sessions`

My unfinished onboardings, so a closed wizard can resume.

### `POST /v1/onboarding/sessions`

Pick a country. Any workspace member can start; creation itself is gated.

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `country` | one of US, IN | yes |

### `POST /v1/onboarding/accounts`

Create my company: opens a new company (pending platform activation) with me as its
owner and starts the wizard inside it. The web app then sends X-Tenant-Id = tenant_id.

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `country` | one of US, IN | yes |

### `DELETE /v1/onboarding/accounts/{tenant_id}`

Throw away my own unfinished company draft (wizard closed before anything was
submitted). Only drafts — no company profile yet — can be discarded; a submitted
company waits for the platform decision. Frees a slot under the 3-pending cap.

| Parameter | In | Type | Required |
|---|---|---|---|
| `tenant_id` | path | uuid | yes |

### `POST /v1/onboarding/sessions/{session_id}/w9`

US step 1: upload the W-9. Format, parsing and EIN uniqueness are validated
before anything is accepted — the session stores the parsed result.

| Parameter | In | Type | Required |
|---|---|---|---|
| `session_id` | path | uuid | yes |

Body (`multipart/form-data`):

| Field | Type | Required |
|---|---|---|
| `file` | string | yes |

### `PATCH /v1/onboarding/sessions/{session_id}`

Company details. US: domain/e-mail/DBA plus optional W-9 corrections.
India: full manual entry with CIN format + uniqueness checks.

| Parameter | In | Type | Required |
|---|---|---|---|
| `session_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `kind` | one of client, prime_vendor, vendor, end_client (optional) |  |
| `kinds` | list of string (optional) |  |
| `step` | integer (optional) |  |
| `domain` | string (optional) |  |
| `company_email` | email (optional) |  |
| `dba` | string (optional) |  |
| `contact_name` | string (optional) |  |
| `contact_phone` | string (optional) |  |
| `manual` | boolean |  |
| `legal_name` | string (optional) |  |
| `business_type` | string (optional) |  |
| `tin_type` | one of ein, ssn (optional) |  |
| `ein` | string (optional) |  |
| `address` | string (optional) |  |
| `city` | string (optional) |  |
| `state` | string (optional) |  |
| `zip` | string (optional) |  |
| `cin` | string (optional) |  |
| `street` | string (optional) |  |
| `pin` | string (optional) |  |

### `POST /v1/onboarding/sessions/{session_id}/moa`

India: the MOA is mandatory. Stored with the session (Phase 1: no parsing).

| Parameter | In | Type | Required |
|---|---|---|---|
| `session_id` | path | uuid | yes |

Body (`multipart/form-data`):

| Field | Type | Required |
|---|---|---|
| `file` | string | yes |

### `POST /v1/onboarding/sessions/{session_id}/email-code`

E-mail a 6-digit code to the company e-mail (proves control of it).

| Parameter | In | Type | Required |
|---|---|---|---|
| `session_id` | path | uuid | yes |

### `POST /v1/onboarding/sessions/{session_id}/email-verify`

Verify Email Code

| Parameter | In | Type | Required |
|---|---|---|---|
| `session_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `code` | string | yes |

### `POST /v1/onboarding/sessions/{session_id}/complete`

Create the company. Every gate must already be green: parsed/valid W-9 or
manual+CIN+MOA, unique tax ID, verified e-mail, and the authorization checkbox.
The creator becomes the company's Super Admin.

| Parameter | In | Type | Required |
|---|---|---|---|
| `session_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `authorized` | boolean |  |

## acceptances

### `GET /v1/acceptances`

Acceptance History

| Parameter | In | Type | Required |
|---|---|---|---|
| `entity_type` | query | string | yes |
| `entity_id` | query | uuid | yes |

### `POST /v1/acceptances`

Record acceptance given outside myTrakIn. The agreement / SOW becomes active; an amendment is applied.

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `entity_type` | string | yes |
| `entity_id` | uuid | yes |
| `accepted_by` | string | yes |
| `note` | string (optional) |  |

## roles & permissions

### `GET /v1/roles`

List Roles

### `POST /v1/roles`

Create Role

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `name` | string | yes |
| `base_role` | one of tenant_admin, finance, account_manager, legal, hr, approver, viewer, vendor_admin, client_user, consultant | yes |
| `permissions` | object |  |

### `PATCH /v1/roles/{role_id}`

Update Role

| Parameter | In | Type | Required |
|---|---|---|---|
| `role_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `name` | string (optional) |  |
| `permissions` | object (optional) |  |

### `DELETE /v1/roles/{role_id}`

Members of a deleted role fall back to their base role's access.

| Parameter | In | Type | Required |
|---|---|---|---|
| `role_id` | path | uuid | yes |

### `PATCH /v1/users/{membership_id}/access`

Give someone a custom role and/or per-module exceptions. A custom role also sets their base role.

| Parameter | In | Type | Required |
|---|---|---|---|
| `membership_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `custom_role_id` | uuid (optional) |  |
| `permission_overrides` | object (optional) |  |

## consultants

### `GET /v1/consultants/engagement-types`

C2C, E2E (employer-to-employer), 1099, W-2 … — from the engagement_types table.

### `GET /v1/consultants/candidates`

Any registered myTrakIn user, to pick from when onboarding a consultant.
Search by name, U-ID or e-mail; every result shows its U-ID.

A consultant must be someone who already has an account somewhere on the platform:
their name, e-mail and mobile come from their profile rather than being typed again,
and the U-ID is what ties them across workspaces. Onboarding adds them to this
workspace. `already_consultant` flags the ones on the books here already,
`in_workspace` the ones who already have access here in some other role.

A term is required (2 characters or more) so this cannot be used to page through
everybody on the platform.

| Parameter | In | Type | Required |
|---|---|---|---|
| `q` | query | string | yes |

### `GET /v1/consultants`

List Consultants

| Parameter | In | Type | Required |
|---|---|---|---|
| `status` | query | string (optional) |  |

### `POST /v1/consultants`

Start onboarding for someone who already has a myTrakIn account. Their name,
e-mail and mobile come from their profile, so a consultant can't be created as a
near-duplicate of a person who is already here under another name. They may be new
to this workspace: onboarding is what gives them access here.

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `user_id` | uuid | yes |
| `engagement` | string | yes |
| `employer_company_id` | uuid (optional) |  |
| `title` | string (optional) |  |
| `location` | string (optional) |  |
| `start_date` | date | yes |
| `skills` | list of string |  |

### `GET /v1/consultants/{consultant_id}`

Get Consultant

| Parameter | In | Type | Required |
|---|---|---|---|
| `consultant_id` | path | uuid | yes |

### `PATCH /v1/consultants/{consultant_id}`

Update Consultant

| Parameter | In | Type | Required |
|---|---|---|---|
| `consultant_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `full_name` | string (optional) |  |
| `email` | email (optional) |  |
| `phone` | string (optional) |  |
| `title` | string (optional) |  |
| `location` | string (optional) |  |
| `work_auth_type` | string (optional) |  |
| `work_auth_expires` | date (optional) |  |
| `i9_status` | string (optional) |  |
| `everify_status` | string (optional) |  |
| `skills` | list of string (optional) |  |

### `POST /v1/consultants/{consultant_id}/checklist`

Tick Checklist

| Parameter | In | Type | Required |
|---|---|---|---|
| `consultant_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `index` | integer | yes |
| `done` | boolean | yes |

### `POST /v1/consultants/{consultant_id}/activate`

Finish onboarding: the consultant becomes active and can submit timesheets.

| Parameter | In | Type | Required |
|---|---|---|---|
| `consultant_id` | path | uuid | yes |

### `POST /v1/consultants/{consultant_id}/offboard`

End all assignments and move the consultant to Former. Nothing is deleted.

| Parameter | In | Type | Required |
|---|---|---|---|
| `consultant_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `last_day` | date | yes |
| `reason` | string | yes |
| `rehire_eligible` | boolean |  |

### `POST /v1/consultants/{consultant_id}/rehire`

Rehire

| Parameter | In | Type | Required |
|---|---|---|---|
| `consultant_id` | path | uuid | yes |

## health

### `GET /v1/health`

Health

### `GET /v1/health/db`

Health Db

