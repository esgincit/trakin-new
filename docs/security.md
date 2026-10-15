# Security and compliance

Audience: security reviewers, customers' IT and compliance teams. Technical detail is in [technical.md §4](technical.md#4-security-model).

## Summary

| Area | Control |
|---|---|
| Hosting | Vercel (web + API) and Supabase (database, auth, files), both SOC 2 Type II; US regions |
| Encryption | TLS 1.2+ in transit (HSTS preload); AES-256 at rest (Supabase managed) |
| Tenant isolation | Postgres row-level security with a restrictive tenant policy on every table; API runs as a non-privileged role |
| Authentication | Supabase Auth: e-mail/SMS one-time codes, SAML SSO, Google, Microsoft, optional password (12+ chars) |
| MFA | TOTP authenticator apps; **the user's choice** (owner decision 2026-10-15). The owner can withhold the option per user; once a user turns it on, every API call needs the second step (`aal2`). |
| Authorization | 10 roles; database policies and API checks must both allow an action |
| Least visibility | Each company sees only its own link of the vendor chain; other parties' amounts are never stored |
| Secrets | Service keys only in server environment variables; tokens and codes stored as SHA-256 hashes |
| Audit | Append-only log of every change with user, role, time, IP, device and before/after values |
| E-signatures | ESIGN/UETA consent, e-mail verification by code, per-step IP/device/location evidence, sealed PDF with SHA-256 |
| Files | Private buckets, 5-minute signed download links; profile photos under unguessable names |
| Web | CSP (self + API + Supabase only), `frame-ancestors 'none'`, nosniff, strict referrer, no indexing |
| Input | Pydantic validation on every endpoint; parameterised SQL only; file type and size checks; CSV exports neutralise spreadsheet formulas (CSV injection) |

## Personal and sensitive data

| Data | Stored | Notes |
|---|---|---|
| Names, e-mails, phones, titles | Yes | Business contact data |
| EIN of companies | Yes | Masked for non-finance roles |
| Work-authorization type and dates, I-9 / E-Verify status | Yes | Status and dates only — **no document images, A-numbers or SSNs**; HR/legal see the type |
| SSN / ITIN / bank account numbers | **No** | Keep in payroll and banking systems |
| Rates and invoices | Yes | Visible by role; consultants never see amounts |
| Signatures | Yes | Typed name or drawn image; excluded from the audit copy |
| IP addresses, device, approximate location | Yes | Audit and e-signature evidence |

Do not upload I-9 supporting documents or passports as attachments unless your policy requires it; if you do, restrict
access to HR and set a retention schedule.

## Compliance notes (not legal advice)

- **ESIGN Act / UETA**: consent disclosure before signing, intent to sign, association of signature with the record,
  retention and reproduction (sealed PDF), and the right to a paper copy are covered.
- **Form I-9**: the app tracks Section 1/2 timing and reverification dates and reminds HR; the form itself is completed in
  your I-9/E-Verify system. C2C vendors are responsible for their own employees.
- **1099-NEC**: year-end summary of payments to individuals with W-9 status; threshold configurable ($600 through 2025,
  $2,000 from 2026 — confirm annually).
- **Worker classification**: the 1099 checklist requires a documented classification review.
- **Privacy laws (e.g. CCPA/CPRA)**: export a person's data from the relevant lists; profiles can be edited by the person;
  deletion on request after retention periods, handled by the platform owner.

## Responsibilities

| | myTrakIn (platform owner) | Customer (workspace admin) |
|---|---|---|
| Infrastructure, patching, backups | ✓ | |
| Application security, RLS, audit | ✓ | |
| User invitations, roles, removals | | ✓ |
| Enforcing MFA for all staff (optional setting) | | ✓ |
| Accuracy of contracts, rates, I-9 data | | ✓ |
| SSO configuration | ✓ (Supabase) | ✓ (identity provider) |

## Incident response

1. Detect (alerts, user report). 2. Contain: lock affected users, rotate keys (Supabase JWT signing key, service key,
`CRON_SECRET`, Resend key), suspend the workspace if needed. 3. Investigate with the audit log (filter by user, IP,
time) and Vercel/Supabase logs. 4. Notify affected customers without undue delay and within contractual/legal deadlines.
5. Post-incident review and fixes.

## Security testing checklist (before go-live and yearly)

- [ ] Outsider (signed in, no invitation) gets `no_access` on every endpoint.
- [ ] Vendor A cannot read Vendor B's invoices, consultants or timesheets (change ids in requests).
- [ ] Consultant responses contain no `bill_rate`, `pay_rate` or amounts.
- [ ] `anon` key cannot query `mytrakin.*` through the Supabase REST endpoint.
- [ ] A user who turned MFA on and signs in without the code receives `mfa_required`; users without MFA are not blocked.
- [ ] Signing links: reused, voided and expired tokens return 404; 6 wrong codes lock the code.
- [ ] Cron endpoint rejects requests without the secret.
- [ ] File links expire after 5 minutes.
- [ ] Dependency audit: `pip-audit -r apps/api/requirements.txt`, `npm audit --omit=dev` in `apps/web`.

Most of these are automated in `apps/api/tests/test_access.py`.
