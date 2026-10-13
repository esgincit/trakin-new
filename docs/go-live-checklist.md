# Go-live checklist

Print it, or copy it into your project tracker. Owner in brackets.

## A. Platform (once) [platform team]

- [ ] Production Supabase project on a paid plan, region chosen, database password in the vault
- [ ] Migrations applied (`supabase db push`); `mytrakin` **not** in exposed schemas
- [ ] Auth: Site URL and redirect URLs; e-mail OTP (6 digits, 10 min); custom SMTP; TOTP MFA on
- [ ] Optional providers configured and tested: SMS, Google, Microsoft, SAML SSO
- [ ] JWT signing keys (ES256) active; API `SUPABASE_JWT_SECRET` empty (or legacy secret set)
- [ ] Vercel API project: root `apps/api`, all env vars, region matches database, `/v1/health/db` OK
- [ ] Vercel web project: root `apps/web`, env vars, custom domain, HTTPS
- [ ] `WEB_ORIGIN` = production web URL; CORS works from the browser
- [ ] Resend domain verified (SPF, DKIM, DMARC); test e-mail received
- [ ] `CRON_SECRET` set; cron visible in Vercel; one manual run returns no errors
- [ ] Vercel Firewall rate-limit rule on `/v1/public/*`
- [ ] Platform owner row inserted; owner console opens
- [ ] Uptime check on `/v1/health/db`; alert routing set
- [ ] Backups confirmed; Storage backup/sync configured
- [ ] Security checklist ([security.md](security.md#security-testing-checklist-before-go-live-and-yearly)) passed

## B. Each new workspace [customer admin + implementer]

**Week 1 — set up**
- [ ] Workspace created; admin signed in and enrolled MFA
- [ ] Company details (legal name, EIN, state) and sign-in methods
- [ ] Users invited with the right roles, reporting lines and approval limits
- [ ] Reminder rules reviewed (days, on/off)
- [ ] Policies published (code of conduct, information security, timesheet & expense, anti-harassment …)

**Week 1–2 — data**
- [ ] Clients & vendors imported (including inactive), contacts' e-mails correct
- [ ] Consultants imported (active, onboarding, former) with engagement types
- [ ] MSAs/subcontracts recorded with PDFs attached; expiry dates checked
- [ ] SOWs with ceilings and amounts invoiced/collected before go-live
- [ ] Projects and placements with AR and AP rates and terms; pay-when-paid flags
- [ ] Open invoices (AR and AP) imported so balances match the accounting system
- [ ] Expiring documents (I-9 reverification, EAD, passports, COIs, W-9s) entered
- [ ] Payroll history (optional), referral agreements
- [ ] Reconciliation: AR and AP totals in myTrakIn = accounting system on the cut-over date

**Week 2 — people**
- [ ] Training sessions held (see [training-guide.md](training-guide.md))
- [ ] Consultants invited; first timesheet week chosen and announced
- [ ] Vendors told about the portal and invoice submission (template e-mail below)
- [ ] Registration link shared for new vendors

**Go-live week**
- [ ] First week of timesheets submitted and approved
- [ ] First invoices generated, checked and sent
- [ ] First vendor invoices matched; first payment run
- [ ] Dashboard and payment flow reviewed with finance
- [ ] Setup checklist step 8 marked → workspace Active

**30 days after**
- [ ] Reminder e-mails reviewed (Compliance → Reminders & e-mails) — any bounces?
- [ ] Audit log spot check
- [ ] Feedback session; adjust roles and rules

## Template: e-mail to vendors

> Subject: New invoice process — myTrakIn
>
> Hello {{name}},
>
> From {{date}} we track timesheets and invoices in myTrakIn. You'll receive an invitation at this address. Once signed
> in you'll see your consultants' approved hours and can submit invoices directly; you'll also see each invoice's status
> through to payment. Please invoice approved hours only — invoices that don't match approved timesheets are held for review.
>
> Questions: {{AP contact}}.
