# myTrakIn API reference

Generated from the code by `scripts/gen-api-reference.py` — do not edit by hand.

Base URL: `https://<your-api-domain>/v1`. Every call except `/public/*`, `/health` and `/cron/*` needs
`Authorization: Bearer <Supabase access token>` and, for workspace data, `X-Tenant-Id: <workspace id>`
(optional when the person belongs to one workspace).

Errors always look like `{"error": {"code": "...", "message": "..."}}`. Common codes: `unauthorized` (401),
`mfa_required`, `forbidden`, `no_access` (403), `not_found` (404), `duplicate`, `conflict` (409), `invalid` (400/422).

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
- [consultants](#consultants)
- [health](#health)

## me

### `GET /v1/me`

Profile, the workspaces this person can open, and whether they own the platform.

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

### `GET /v1/companies`

List Companies

| Parameter | In | Type | Required |
|---|---|---|---|
| `kind` | query | string (optional) |  |
| `status` | query | string (optional) |  |

### `POST /v1/companies`

Create Company

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `name` | string | yes |
| `kind` | one of client, prime_vendor, vendor, end_client | yes |
| `ein` | string (optional) |  |
| `state` | string (optional) |  |
| `address` | string (optional) |  |
| `contact_name` | string (optional) |  |
| `contact_email` | email (optional) |  |
| `contact_phone` | string (optional) |  |
| `default_terms` | string |  |
| `notes` | string (optional) |  |

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
| `kind` | one of client, prime_vendor, vendor, end_client (optional) |  |
| `ein` | string (optional) |  |
| `state` | string (optional) |  |
| `address` | string (optional) |  |
| `contact_name` | string (optional) |  |
| `contact_email` | email (optional) |  |
| `contact_phone` | string (optional) |  |
| `default_terms` | string (optional) |  |
| `notes` | string (optional) |  |
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
| `code` | string | yes |
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

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `code` | string | yes |
| `agreement_id` | uuid | yes |
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

### `GET /v1/projects`

List Projects

### `POST /v1/projects`

Create Project

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `code` | string | yes |
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
| `code` | string | yes |
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
| `file` | string (optional) |  |
| `document_path` | string (optional) |  |

### `GET /v1/envelopes/{envelope_id}`

Get Envelope

| Parameter | In | Type | Required |
|---|---|---|---|
| `envelope_id` | path | uuid | yes |

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

### `DELETE /v1/users/{membership_id}`

Withdraw an invitation that hasn't been accepted. Active users are deactivated instead (history is kept).

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

Metrics

### `GET /v1/platform/tenants`

Tenants

### `POST /v1/platform/tenants`

Create a workspace and invite its first admin.

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `name` | string | yes |
| `legal_name` | string (optional) |  |
| `ein` | string (optional) |  |
| `state` | string (optional) |  |
| `plan` | one of starter, growth, enterprise |  |
| `admin_email` | email | yes |
| `admin_name` | string (optional) |  |
| `trial` | boolean |  |

### `PATCH /v1/platform/tenants/{tenant_id}`

Change plan, extend a trial, suspend (users can't sign in) or close a workspace.

| Parameter | In | Type | Required |
|---|---|---|---|
| `tenant_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `plan` | one of starter, growth, enterprise (optional) |  |
| `status` | one of onboarding, active, suspended, closed (optional) |  |
| `trial_ends_on` | date (optional) |  |

### `GET /v1/platform/signups`

Signups

| Parameter | In | Type | Required |
|---|---|---|---|
| `status` | query | string (optional) |  |

### `POST /v1/platform/signups/{signup_id}/decision`

Decide Signup

| Parameter | In | Type | Required |
|---|---|---|---|
| `signup_id` | path | uuid | yes |

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `decision` | one of approved, rejected, needs_info | yes |
| `note` | string (optional) |  |
| `plan` | one of starter, growth, enterprise (optional) |  |

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

### `POST /v1/public/signups`

A staffing company asks for a workspace. The platform owner approves it.

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `company` | string | yes |
| `contact_name` | string | yes |
| `email` | email | yes |
| `phone` | string (optional) |  |
| `state` | string (optional) |  |
| `ein` | string (optional) |  |
| `plan` | one of starter, growth, enterprise |  |
| `seats` | integer |  |

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

## consultants

### `GET /v1/consultants`

List Consultants

| Parameter | In | Type | Required |
|---|---|---|---|
| `status` | query | string (optional) |  |

### `POST /v1/consultants`

Start onboarding. The checklist depends on the engagement type.

Body (`application/json`):

| Field | Type | Required |
|---|---|---|
| `full_name` | string | yes |
| `email` | email | yes |
| `phone` | string (optional) |  |
| `engagement` | one of w2_fulltime, w2_contract, c2c, 1099 | yes |
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

