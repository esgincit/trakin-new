# Deployment and operations

Audience: whoever deploys and runs myTrakIn. Time for a first production deployment: about two hours.

You will create:

| Thing | Where | Notes |
|---|---|---|
| Supabase project (one per environment) | supabase.com | Postgres, Auth, Storage. Region near your users, e.g. `us-east-1`. |
| Vercel project **mytrakin-api** | vercel.com | Root directory `apps/api` |
| Vercel project **mytrakin-web** | vercel.com | Root directory `apps/web` |
| Resend account + verified sending domain | resend.com | For all e-mail |
| DNS records | your DNS host | e.g. `app.yourdomain.com` → web, `api.yourdomain.com` → API |

Use separate **staging** and **production** Supabase projects and Vercel environments.

## 1. Supabase

### 1.1 Create the project
1. New project → name `mytrakin-prod`, strong database password (store it in your password manager), region `us-east-1`
   (if you choose another region, pick the matching Vercel region in §2.3).
2. Plan: Pro or above for production (daily backups, no pausing; SAML SSO and point-in-time recovery are add-ons/higher tiers).

### 1.2 Apply the database
From your machine (or the *Database migrations* GitHub workflow):

```bash
npm i -g supabase            # or brew install supabase/tap/supabase
supabase login
supabase link --project-ref <project-ref>
supabase db push             # applies supabase/migrations in order
```

Do **not** run `supabase/seed.sql` in production. For staging/training: `psql "$DIRECT_URL" -f supabase/seed.sql`
after changing the e-mail addresses at its top.

Check it worked (SQL editor):

```sql
select count(*) from pg_tables where schemaname = 'mytrakin';      -- about 40
select rolname, rolbypassrls from pg_roles where rolname = 'mytrakin_api';  -- false
```

### 1.3 Keep the schema private
*Project Settings → Data API → Exposed schemas* must **not** include `mytrakin` (the default list is fine).

### 1.4 Authentication
*Authentication → URL configuration*
- Site URL: `https://app.yourdomain.com`
- Redirect URLs: `https://app.yourdomain.com/login`, plus your staging and preview URLs.

*Authentication → Sign In / Providers*
- **Email**: enabled; *Confirm email* on. Set the e-mail OTP length to 6 and expiry to 600 s.
- **Phone** (optional): pick an SMS provider (Twilio, MessageBird, Vonage, Textlocal) and enter its credentials.
- **Google** / **Azure (Microsoft)** (optional): create OAuth apps, paste client id/secret; callback URL is shown in Supabase.
- **SAML SSO** (per enterprise customer): `supabase sso add --type saml --metadata-url <IdP metadata> --domains customer.com`.

*Authentication → Emails → SMTP*: use Resend's SMTP (or any provider) so sign-in codes come from your domain.
Edit the *Magic link / OTP* template so it shows `{{ .Token }}` (the 6-digit code).

*Authentication → Multi-factor*: TOTP enabled (enroll + verify).

*Project Settings → JWT keys*: prefer the asymmetric signing keys (ES256). The API verifies them through
`https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json` automatically when `SUPABASE_JWT_SECRET` is empty.
Projects still on the legacy secret: copy it into `SUPABASE_JWT_SECRET`.

### 1.5 Storage
Migration 0500 creates three buckets: `documents` (private), `esign` (private, PDF only), `avatars` (public read,
images only, 5 MB). Nothing else to do.

### 1.6 Connection strings
*Connect* button → copy:
- **Transaction pooler** (port **6543**) → the API's `DATABASE_URL` (add `?sslmode=require`).
- **Direct connection** (port 5432) → only for migrations and `psql`.

## 2. Vercel

### 2.1 API project
1. *Add New → Project* → import the repository → **Root Directory `apps/api`**. Framework preset: FastAPI (detected from
   `pyproject.toml` → `[tool.vercel] entrypoint = "app.main:app"`).
2. Environment variables (Production and Preview; values from §1):

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` (staging: `staging`) |
| `DATABASE_URL` | transaction pooler URL, port 6543, `?sslmode=require` |
| `DB_POOL` | `none` |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `SUPABASE_JWT_SECRET` | empty with signing keys; legacy secret otherwise |
| `SUPABASE_SERVICE_ROLE_KEY` | service-role / secret key (server only) |
| `WEB_ORIGIN` | `https://app.yourdomain.com` |
| `EXTRA_CORS_ORIGINS` | staging/preview web URLs, comma-separated |
| `RESEND_API_KEY` | from Resend |
| `EMAIL_FROM` | `myTrakIn <no-reply@yourdomain.com>` (domain verified in Resend) |
| `CRON_SECRET` | `openssl rand -hex 32` |
| `ANTHROPIC_API_KEY` | optional |
| `REQUIRE_MFA_FOR_MONEY_ROLES` | `true` |

3. Deploy. Check `https://<api-domain>/v1/health` and `/v1/health/db` (shows database latency in ms).

`vercel.json` sets the region (`iad1`), `maxDuration` 60 s and the daily cron (`/v1/cron/daily` at 13:00 UTC). Vercel sends
`Authorization: Bearer $CRON_SECRET`; the API rejects anything else. On the Hobby plan crons run once a day within the
hour; Pro runs them on the minute.

### 2.2 Web project
1. Import the same repository again → **Root Directory `apps/web`**, framework Next.js.
2. Environment variables:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://api.yourdomain.com` |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | anon / publishable key (safe in the browser — it can't reach the `mytrakin` schema) |

3. Deploy and open `/login`.

### 2.3 Region and performance
Both projects run in `iad1` (Washington, D.C.), next to Supabase `us-east-1`. If your database is elsewhere, change
`regions` in both `vercel.json` files to the closest Vercel region — every API call does several database round trips,
so this matters more than anything else for speed.

### 2.4 Rate limits for public endpoints
Sign-up, registration and signing-code endpoints work without an account. In the API project →
*Firewall → Rules*, add a rate-limit rule: path starts with `/v1/public/`, 30 requests per minute per IP, action
*Deny* (Vercel Firewall rate limiting is available on Pro and above). The API also limits signing codes to one per
45 seconds and five wrong attempts per code.

### 2.5 Domains
*Project → Settings → Domains*: `app.yourdomain.com` on the web project, `api.yourdomain.com` on the API project.
Update `WEB_ORIGIN`, the Supabase Site URL and redirect URLs to match, then redeploy the API.

## 3. First run

1. Open `https://app.yourdomain.com/login`, sign in with **your** e-mail (code). You'll see *Almost there* — expected.
2. Make yourself platform owner (Supabase SQL editor):

   ```sql
   insert into mytrakin.platform_admins (user_id)
   select id from auth.users where email = 'you@yourdomain.com';
   ```

3. Reload — **Owner console** appears. *Create workspace* for your first customer (or your own company) with its
   admin's e-mail. The admin receives an invitation.
4. The admin signs in, sets up MFA and follows the setup checklist ([go-live-checklist.md](go-live-checklist.md)).

## 4. Training environment

A separate Supabase project + Vercel preview/staging deployment:

```bash
supabase link --project-ref <training-ref> && supabase db reset --linked   # drops everything, re-applies migrations
psql "$TRAINING_DIRECT_URL" -f supabase/seed.sql                            # demo workspace
```

Edit the e-mail addresses at the top of `seed.sql` first; each becomes an invitation claimed at first sign-in. Add the
platform owner row as in §3. Reset before each class.

## 5. Releases

1. Pull request → CI runs ruff, the API tests (against a database built from the migrations) and the web build.
2. Merge → Vercel deploys both apps to production automatically (previews for every branch).
3. Database changes: run **Actions → Database migrations → staging**, test, then **production** (protect the
   `production` GitHub environment with required reviewers). Always deploy migrations **before** code that needs them,
   and write migrations that old code can live with (add columns nullable, backfill, then tighten).
4. Rollback: Vercel → Deployments → *Instant Rollback*. Database changes are rolled forward with a new migration;
   restore from backup only for data loss.

## 6. Monitoring

| What | Where |
|---|---|
| API errors and latency | Vercel → mytrakin-api → Logs / Observability; every response has `Server-Timing: app;dur=…` |
| Cron runs | Vercel → Settings → Cron Jobs → *View logs*; the JSON response lists e-mails sent per workspace |
| Database load, slow queries | Supabase → Reports, Query performance |
| E-mail delivery | Resend dashboard; myTrakIn's own log under Compliance → Reminders & e-mails |
| Uptime | Any uptime checker on `/v1/health/db` every 5 minutes |
| Usage and revenue | Owner console |

Suggested alerts: API 5xx rate > 1 % for 5 min; `/v1/health/db` failing twice; cron response containing `"error": true`.

## 7. Backups and data retention

- Supabase daily backups (Pro: 7 days; add point-in-time recovery for production).
- Monthly: restore the latest backup into a scratch project and run the API tests against it.
- Storage (documents, signed PDFs) is not in database backups — enable Storage backups or sync the buckets to your own
  S3 with a scheduled job.
- Keep audit logs and signed agreements for at least the contract term + 7 years (adjust with counsel). Form I-9 must be
  kept 3 years after hire or 1 year after employment ends, whichever is later.

## 8. Runbook

| Symptom | Likely cause | Fix |
|---|---|---|
| Everyone gets 401 | Wrong `SUPABASE_URL` / JWT secret, or keys rotated | Check API env; with signing keys leave `SUPABASE_JWT_SECRET` empty; redeploy |
| "Can't reach myTrakIn" in the browser | CORS origin missing or API down | Add the web URL to `WEB_ORIGIN`/`EXTRA_CORS_ORIGINS`; check `/v1/health` |
| 500s mentioning prepared statements | Direct URL used instead of the pooler, or pgbouncer settings | Use the transaction pooler URL (6543) |
| `permission denied for schema mytrakin` in API logs | Migrations not applied or role grant missing | `supabase db push`; check `grant mytrakin_api to postgres` |
| No e-mails | `RESEND_API_KEY` empty or domain not verified | Set key, verify domain; check Resend logs |
| Sign-in codes don't arrive | Supabase SMTP not configured / rate limits | Configure custom SMTP; raise auth e-mail rate limit |
| Reminders didn't go out | Cron disabled, wrong `CRON_SECRET`, or Hobby-plan timing | Vercel → Cron Jobs; run once by hand: `curl -H "Authorization: Bearer $CRON_SECRET" https://api…/v1/cron/daily` |
| User lost their authenticator | — | Supabase → Authentication → Users → user → remove the MFA factor; they enroll again at next sign-in |
| Customer wants to leave | — | Export all data sets (Import & export), then owner console → Closed; delete on request after the retention period |
| Suspected account compromise | — | Users & roles → Locked; Supabase → sign the user out; review the audit log by IP address |

## 9. Cost guide (October 2026 list prices — check current pricing)

Supabase Pro ≈ $25/month per project + usage; Vercel Pro ≈ $20 per member/month + usage; Resend from free (3k e-mails/month)
to ≈ $20/month. A workspace of 50 users fits comfortably in the base tiers.
