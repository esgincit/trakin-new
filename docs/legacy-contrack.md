# Carry-over from the old project (Contrack / "MyTrakinFB")

The team's earlier product lives at `C:\Users\funny\Documents\ESG\MyTrakinFB\Contrack-Monorepo` (Django + React,
deployed on Azure, domain **mytrakin.com**). myTrakIn (this repo) replaces it.

> **Rule (owner's instruction, 2026-10-13): do not copy or implement functionality from the old project.**
> The prototype in `docs/prototype/` is the only requirement. From the old project we keep **only** (1) infrastructure
> and service settings and (2) engineering/security lessons. If the old app had a feature that the prototype does not
> have, it is *not* built here — do not add it, do not propose it as backlog, do not copy its code.

**Azure is closed (2026-10-13).** At the owner's request the whole `rg-contrack` resource group in "Azure subscription
1" (tenant ESG INC) was deleted: 2 always-on Premium App Service plans + the apps `mytrakinprod` (Australia East) and
`contrack-esg-r620lc` (Central India), container registry `contrackacrfypuez`, two AI Services accounts (with Claude
deployments), Application Insights / Log Analytics, two App Service certificates and a managed identity. The
subscription now has no resource groups. Nothing was exported first (owner: nothing needed from Azure). The AI
Services accounts are soft-deleted (not billed, restorable ~48 days). The old source is still on GitHub
(`mytrackin/Contrack-Monorepo`). **Left to do by the owner:** remove the `mytrakin.com` DNS records that still point at
Azure (see PLAN §9, 2026-10-13) and disable the old repo's Azure deploy workflows.

Read on 2026-10-13. **No secrets are recorded here.** Credentials stay in `.env` files and Vercel environment
variables, never in git or docs. If someone needs the old values they are in `Contrack-Monorepo\Backend\.env`.

---

## 1. Settings we keep

### 1.1 E-mail through Zoho SMTP — already in place
| Setting | Value | Note |
|---|---|---|
| `EMAIL_HOST` | `smtp.zoho.in` | Zoho **India** data centre. A `.com` / `.eu` Zoho account uses `smtp.zoho.com` / `smtp.zoho.eu`. |
| `EMAIL_PORT` | `587` | STARTTLS |
| `EMAIL_USE_TLS` | `true` | (old project also set `EMAIL_USE_SSL=False`) |
| `EMAIL_HOST_USER` | the full sender mailbox | Zoho only lets you send *from* the mailbox you log in with (or its aliases). |
| `EMAIL_FROM` | `myTrakIn <same mailbox>` | |
| `EMAIL_HOST_PASSWORD` | mailbox password, or an **app-specific password** if two-factor is on | secret — env var only |

- The new API already sends this way (`apps/api/app/services/email.py`: Resend if `RESEND_API_KEY` is set, otherwise
  plain SMTP) and logs every message in `notifications` with de-duplication. Nothing to build.
- **One open question, D9:** the old project sent from `verify@mytrakin.com`; the new local `.env` sends from
  `verify@esgos.app`. Which domain is the production sender? Whichever it is, add SPF, DKIM and DMARC for it in Zoho,
  or verification codes and reminders will land in spam.

### 1.2 Services (for the decisions already open in PLAN §6)
- **SMS provider (D7):** the only one the team has used is **Twilio** (Verify service for SMS codes). If SMS is wanted
  — the prototype already lists SMS sign-in and SMS reminders — Twilio is the default choice. Needs
  `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SERVICE_SID`. Supabase Auth also has Twilio built in for
  SMS sign-in.
- **AI providers (D3):** the old app used several (Anthropic, OpenAI, Gemini, Azure OpenAI, free OpenCode models). The
  new product keeps only Anthropic and DeepSeek.
- **Not carried:** Redis, RabbitMQ, Celery, Elasticsearch, Firebase, Azure Container Registry / App Service,
  LinkedIn OAuth, Sentry wiring. (Hosting is Vercel + Supabase; scheduled jobs are Vercel Cron.)

### 1.3 Things deliberately not reused
- **Branding:** old accent was teal `#51B1AB`; the prototype is blue `#1f4fd6` — follow the prototype.
- **Data:** the old database is a different Supabase project and is not migrated. Old currencies were USD and INR; the
  prototype is USD only.
- **Form PDFs / templates** in the old `Frontend/public` (I-9, W-9, MoA): do not copy; forms go out of date. Link to the
  current IRS / USCIS downloads where the prototype needs a blank form.

---

## 2. Security & engineering lessons (checklist, not features)

The old project's security audit (2026-07-19) ended in "BLOCK". These are mistakes not to repeat in code we are already
writing for prototype features. Status in the new code was checked by reading it on 2026-10-13: ✅ handled · 🟡 partly /
verify · ❓ not checked yet. Tracked as `SEC-*` in PLAN.md §5.29 and verified in Phase 0.

| ID | Old mistake | Rule for myTrakIn | Status |
|---|---|---|---|
| SEC-01 | One-time codes from a non-secure random generator | Use `secrets` for every code | ✅ `utils.otp_code` |
| SEC-02 | No throttling on login / reset / code verify; unlimited guesses | Per-code attempt limit **and** app-level rate limits on `/v1/public/*` and any endpoint that sends or checks a code | 🟡 attempts (5) and hashed codes exist for e-sign; no general rate limiting (only a Vercel Firewall rule in the go-live list) |
| SEC-03 | Code-resend flooding | Per recipient: 60 s cooldown and at most 5 sends/hour | 🟡 e-sign has a cooldown; verify everywhere codes are sent |
| SEC-04 | Wrong guesses never burned the code; plain `==` comparison | After 5 wrong tries burn the code; constant-time compare (`hmac.compare_digest`) | 🟡 verify the compare |
| SEC-05 | Sign-up / forgot-password revealed whether an account exists | Identical response either way; mail errors never leak existence | ❓ |
| SEC-06 | A reset code had no expiry check | Every code has an expiry, checked on use | ✅ e-sign; ❓ rest |
| SEC-07 | **Self-approval:** approver derived from the submitter, no check approver ≠ requester | One guard before every approval write (timesheet, expense, time off, AP exception, payment run, bank change, referral): approver ≠ requester, and for dual approval second ≠ first | ❓ check `timesheets.approve` and the rest — one person can be both admin and consultant |
| SEC-08 | Role change wrote the higher role *before* validating, then errored but kept the row | Validate the target role against the caller's role **before** any write; fail the whole transaction | ❓ check `users` endpoints |
| SEC-09 | 90-day access tokens | Short-lived tokens | ✅ Supabase default (1 hour) |
| SEC-10 | Tokens in `localStorage` | Supabase JS keeps the session in browser storage (`persistSession: true`) — an XSS would expose it | 🟡 add a strict Content-Security-Policy; consider cookie sessions (`@supabase/ssr`) |
| SEC-11 | A pull request could trigger a production deploy (`workflow_run` matched the head branch *name*) | Production deploy only for a `push` to `main`; never run PR code with secrets | 🟡 check `.github/workflows` before adding any deploy workflow |
| SEC-12 | No upload validation; an uploaded SVG served inline = stored XSS | Allow-list extensions and content types, size cap, sniff content server-side, serve user files as `attachment`, never render uploaded SVG/HTML inline | 🟡 size cap + PDF check only |
| SEC-13 | Endpoints that never scoped by user/company → cross-tenant leaks | Every query scoped by tenant (RLS) **and** by party (vendor sees own, AM sees assigned); one two-tenant test per router | ✅ RLS; 🟡 party scoping (ACC-03) |
| SEC-14 | CSV/XLSX export formula injection | Prefix cells starting `= + - @` | ✅ `csv_io._cell` |
| SEC-15 | Unpinned dependencies; `npm install` in CI | Lockfiles, `npm ci`, pinned Python versions | 🟡 `package-lock.json` present; check Python pins |
| SEC-16 | A private key committed to git history | No secrets in git; run a secret scan on this repo once | ❓ |
| SEC-17 | Unpaginated list endpoints | Every list endpoint paginated or limited | 🟡 |
| SEC-18 | Unlimited AI usage per user | Cap AI spend and calls per user on the existing "Ask" box | ❓ |

---

## 3. Billing correctness rules → acceptance tests for features the prototype already has

The old QA suite proved these. They are **tests**, not features: write each as an API test when touching the matching
prototype item (AR-01 invoices from timesheets, AR-05 payments, AR-09 void, PRJ-04 rate change, TS approvals). The old
multi-company "billing event" model and dispute workflow are not used.

| ID | Rule |
|---|---|
| BILL-01 | Only **approved** timesheets are billed; rejected ones never are. |
| BILL-02 | Billed hours are the approved hours, not the raw logged hours. |
| BILL-03 | Overlapping invoice periods for the same placement are rejected. |
| BILL-04 | Money is exact decimals — never floating point. |
| BILL-05 | A rate change applies only from its effective date; time before it keeps the old rate. |
| BILL-06 | Re-approving the same timesheet never bills twice. |
| BILL-07 | A later rate change never rewrites amounts already invoiced. |
| BILL-08 | A final invoice or payment is changed only by an adjustment (credit note / correction), never by editing history. |
| BILL-09 | A timesheet row's project must belong to that consultant's own placement. |
| BILL-10 | Rejecting a timesheet leaves nothing billable from it. |
| BILL-11 | Part payments move an invoice open → part paid → paid. |
| BILL-12 | Reminders use the due date and skip paid invoices. |
| BILL-13 | Every money-touching action is audited, including system-run ones with no user. |
| BILL-14 | Margin = what you bill − what you pay, and works from approved time before anything is invoiced. |

---

## 4. Explicitly NOT carried (so nobody re-adds it)
Dropdown-code endpoint · proof-of-payment upload and payment-verification methods · receiver "Received / Not received"
verification and disputes · leave/time-off tied to contracts/projects · help center, support tickets, chatbot hand-off ·
work-anniversary posts · sensitive-document one-time-code gate · data-erasure command · LinkedIn import · business
analytics screens beyond the prototype's Reports · multi-company invoice chains and billing events · invoice template
designer · contract rates table and multi-project contracts · the old feed / connections / messaging · Copilot assistant
PRD · Teams / Slack / Jira / SSO / VPN integrations. If the owner later wants any of these, they must first appear in the
prototype spec.
