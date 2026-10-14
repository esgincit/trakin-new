# Changelog

## Unreleased

- Sign-in: forgot-password flow (`/reset-password`); Google and Microsoft buttons on sign-in and create-account
  (hidden while a provider is switched off in Supabase); clearer sign-in error messages; "cancel and sign out" on the
  two-step verification screen. Setup steps: `docs/auth-setup.md`.

## 1.0.0 — 2026-10-12

First production release of **myTrakIn** (renamed from the VendorChain prototype).

- Multi-tenant SaaS with owner console, sign-up approval, plans and revenue per user
- Payment flow across the vendor chain with the AR/AP-only rule
- AR invoices from approved timesheets, collections, reminders; AP with three-way match, pay-when-paid, payment runs
- Weekly multi-project timesheets with automatic checks and bulk approval
- Onboarding for W-2 full-time, W-2 contract, C2C and 1099; offboarding, former staff, rehire
- MSAs, subcontracts, NDAs, offers, contractor agreements, SOWs and amendments; record existing contracts
- E-signatures with e-mail code, ESIGN/UETA consent, IP/device/location evidence and sealed PDF certificate
- Compliance: I-9 / work authorization, expiring documents with automatic e-mails, policies, public registration
- W-2 payroll records, referral fees, 1099 year-end summary, expenses and time off
- CSV templates, dry-run import, export for every data set
- LinkedIn-style profiles, connections, posts and messages
- Smart suggestions with optional AI answers
- Audit log of every change with IP address and before/after values
- Next.js 16 web app and FastAPI API on Vercel; Supabase Postgres (RLS), Auth (codes, SSO, OAuth, MFA) and Storage
