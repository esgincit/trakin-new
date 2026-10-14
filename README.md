# myTrakIn

Payments, timesheets, contracts and compliance for US staffing companies that sit in a vendor chain
(end client → prime vendor → you → C2C vendor / 1099 contractor / W-2 employee).

myTrakIn tracks **your two links of the chain only** — what your customer owes you (AR) and what you owe your
vendor or contractor (AP). Other layers are shown by name with a masked amount and are never stored.

It runs as a multi-tenant SaaS: each staffing company gets its own workspace; the platform owner sees every
workspace, its progress and revenue per user.

| | |
|---|---|
| Web app | Next.js 16 (App Router, TypeScript), deployed on Vercel |
| API | Python 3.12+ / FastAPI, deployed on Vercel (Fluid compute) |
| Database, sign-in, files | Supabase — Postgres with row-level security, Auth (e-mail/SMS codes, SSO, Google, Microsoft, MFA), Storage |
| E-mail | Resend |
| Scheduled jobs | Vercel Cron (daily reminders) |

## What's in the box

- **Payment flow** — every consultant, period and invoice in the chain with live status (paid, open, held, overdue, mismatch).
- **AR and AP invoices** — generated from approved timesheets, three-way match for vendor invoices, pay-when-paid holds that
  release automatically, payment runs, collection notes, automatic reminders.
- **Timesheets** — one per consultant per week across any number of projects, automatic checks, bulk approval of clean weeks.
- **Onboarding** — W-2 full-time, W-2 contract, C2C and 1099 checklists; former employees and resigned contractors are kept.
- **Contracts** — MSAs, subcontracts, NDAs, offers, contractor agreements, SOWs, amendments; existing contracts can be recorded.
- **E-signatures** — e-mail code, ESIGN/UETA consent, typed or drawn signature, IP address, device and location on every step,
  sealed PDF with certificate of completion.
- **Compliance** — I-9 / E-Verify / work-authorization tracking, expiring documents with automatic e-mails, policies with
  acceptance tracking, public registration with approval.
- **Import & export** — CSV templates with sample rows for every entity; dry-run checks; exports in the same columns.
- **Network** — LinkedIn-style profiles with photos, connections, posts and messages across companies.
- **Smart suggestions** — ranked to-do list from the data, with optional plain-English answers (Anthropic API).
- **Audit log** — every change, who, when, from which IP address, before and after.

## Repository

```
apps/api        FastAPI service (app/, tests/, requirements.txt, vercel.json)
apps/web        Next.js web app (src/app = pages, src/components, src/lib)
supabase/       migrations (schema, RLS, functions), seed.sql (demo data), config.toml
scripts/        local database reset, API reference generator
docs/           technical, functional, user manual, training, deployment, security, go-live, API reference
.github/        CI (lint, tests against real migrations, web build) and a manual migration workflow
```

## Run it locally (about 10 minutes)

Requirements: Python 3.12+, Node 20.9+, PostgreSQL 15+ client tools, and either a local Postgres or the Supabase CLI.

```bash
make setup                                    # Python venv + npm install
make db-reset TEST_DB=postgresql://postgres@localhost:5432/mytrakin_dev   # schema + demo data
cp apps/api/.env.example apps/api/.env        # set DATABASE_URL, SUPABASE_URL, SUPABASE_JWT_SECRET
cp apps/web/.env.example apps/web/.env.local  # set NEXT_PUBLIC_* values
make api                                      # http://localhost:8000/docs
make web                                      # http://localhost:3000
```

Sign-in needs a Supabase project (free tier is fine for development). With the Supabase CLI, `supabase start`
runs Postgres, Auth and Storage locally and applies `supabase/migrations` and `supabase/seed.sql` for you.

Tests: `make test` (builds a fresh database from the migrations every run). Everything CI runs: `make check`.

## Deploy

Short version — the full, click-by-click guide is [docs/deployment.md](docs/deployment.md):

1. Create a Supabase project; apply the migrations (`supabase db push`); turn on the sign-in methods you want.
2. Create two Vercel projects from this repository: root `apps/api` and root `apps/web`. Put both in the region
   closest to your Supabase database (default `iad1` ↔ Supabase `us-east-1`).
3. Set the environment variables from the two `.env.example` files.
4. Make yourself platform owner (one SQL line), create the first workspace from the owner console.
5. Work through [docs/go-live-checklist.md](docs/go-live-checklist.md).

## Documentation

| Document | For |
|---|---|
| [Project plan](docs/PLAN.md) | Everyone on the team — requirement IDs, status, work order, open decisions |
| [Prototype spec](docs/prototype-spec.md) | Builders — every screen, field, rule and formula of the [requirement prototype](docs/prototype/mytrakin-prototype.html) |
| [Functional specification](docs/functional.md) | Product owners, implementers — what every module does and the business rules |
| [Technical documentation](docs/technical.md) | Developers — architecture, data model, security model, how to extend |
| [User manual](docs/user-manual.md) | Everyone — step-by-step by role |
| [Training guide](docs/training-guide.md) | Trainers and new customers — sessions, exercises, quizzes |
| [Deployment & operations](docs/deployment.md) | DevOps — Supabase, Vercel, DNS, monitoring, backups, runbook |
| [Security & compliance](docs/security.md) | Security reviewers, customers' IT |
| [Go-live checklist](docs/go-live-checklist.md) | Whoever launches a workspace |
| [API reference](docs/api-reference.md) | Integrators (generated from code) |

Word versions of the user manual, training guide and functional specification are in [docs/word](docs/word) for
sharing with customers (regenerate with `pandoc docs/<name>.md -o docs/word/myTrakIn-<name>.docx --toc`).

## Name

The product name is written **myTrakIn** everywhere (API `app_name`, page titles, logo, e-mails, PDFs).
A different spelling or brand is a single search-and-replace across `apps/` — there are no other references.

## License

Proprietary — © Executive Software Guild Inc. All rights reserved.
