# Sign-in setup: Google, Microsoft and two-step verification

The code is finished (PLAN.md AUTH-01, AUTH-11, AUTH-12). What is left is **typing values into services we can't
reach from the repo**. Do the steps in order; no code change is needed. No secrets are written in this file.

## The web address

| What | Value | Where I got it |
|---|---|---|
| **Web address (WEB)** | **`https://www.mytrackin.com`** | It serves the sign-in page; `mytrackin.com` redirects to it; the deployed API accepts browser calls from exactly this origin (tested 2026-10-14). |
| API address | `https://trakin-new.vercel.app` | Vercel project `trakin-new` (health check OK). |
| Web Vercel project | `app.mytrakin123` | GitHub deployment list. |
| Supabase project | `pcxewovgpnmbpehlqiqg` | `.env`. |

Careful with spelling: **`mytrackin.com` (c-k-i-n) is the new app.** `mytrakin.com` (k-i-n) was the old Azure site — its
DNS now points at nothing, and it is also the old mail sender `verify@mytrakin.com`. Use the **`ck`** spelling below.
Use **no trailing slash** in Supabase. (`WEB_ORIGIN=https://app.mytrakin123.vercel.app/` in the local `apps/api/.env`
is stale — that address no longer exists; for local work use `http://localhost:3000`.)

The address Google and Microsoft send people back to is Supabase's own:

```
https://pcxewovgpnmbpehlqiqg.supabase.co/auth/v1/callback
```

---

## Step 1 — Supabase: URL Configuration
Dashboard → project → **Authentication → URL Configuration**

| Field | Type exactly |
|---|---|
| **Site URL** | `https://www.mytrackin.com` |
| **Redirect URLs** (press *Add URL* once per line) | `https://www.mytrackin.com/login` |
| | `https://www.mytrackin.com/reset-password` |
| | `http://localhost:3000/login` |
| | `http://localhost:3000/reset-password` |

(Shortcut: two wildcard entries `https://www.mytrackin.com/**` and `http://localhost:3000/**` do the same.) Save.
Without this, Google/Microsoft sign-in and the forgot-password link fail with "redirect not allowed".

## Step 2 — Supabase: Microsoft ("Azure")
Dashboard → **Authentication → Sign In / Providers → Azure** (shown as *Azure (Microsoft)*)

| Field | Type exactly |
|---|---|
| **Enable Sign in with Azure** | switch **on** |
| **Application (client) ID** | `32328f1e-a9a5-43cf-943f-b40f26e82527` |
| **Secret Value** | open `C:\Users\funny\Documents\ESG\_secrets\microsoft-signin.json` and copy the value of `"client_secret"` (valid until 2028-10-13) |
| **Azure Tenant URL** | leave **empty** (accepts work/school and personal Microsoft accounts). Only if you want ESG INC accounts *only*, enter `https://login.microsoftonline.com/<ESG INC tenant id>/v2.0` — the tenant id is in the same JSON file. |

Save. The read-only **Callback URL** the dashboard shows must equal the callback address above (it already is
registered on the Microsoft app — nothing to do in Azure).

## Step 3 — Google (you create it, then paste it in Supabase)
**3a. Google Cloud Console** → *APIs & Services* → **OAuth consent screen**

| Field | Type exactly |
|---|---|
| User type | External |
| App name | `myTrakIn` |
| User support e-mail / Developer contact | your own address |
| Application home page | `https://www.mytrackin.com` |
| Authorised domains | `mytrackin.com` and `supabase.co` |
| Scopes | `openid`, `…/auth/userinfo.email`, `…/auth/userinfo.profile` (the default three) |
| Publishing status | **In production** (otherwise only listed test users can sign in) |

**3b.** *Credentials* → **Create credentials → OAuth client ID** → type **Web application**, name `myTrakIn web`

| Field | Type exactly |
|---|---|
| Authorised JavaScript origins | `https://www.mytrackin.com` |
| | `http://localhost:3000` |
| Authorised redirect URIs | `https://pcxewovgpnmbpehlqiqg.supabase.co/auth/v1/callback` |

Create → copy the **Client ID** and **Client secret**.

**3c. Supabase** → Authentication → Sign In / Providers → **Google**

| Field | Type exactly |
|---|---|
| **Enable Sign in with Google** | switch **on** |
| **Client IDs** | the Client ID from 3b |
| **Client Secret (for OAuth)** | the Client secret from 3b |
| Skip nonce checks / Allow users without an email | leave **off** |

Save.

## Step 4 — Supabase: two-step verification
Dashboard → **Authentication → Multi-Factor** (or *Sign In / Providers → Multi-Factor* in the newer layout)
- **TOTP (Authenticator app)**: *Enroll* **on** and *Verify* **on** (both default to on). Save if shown.

The app already enrols on first use, asks for the code after any first sign-in step (e-mail code, password, Google,
Microsoft, SSO), and the API refuses any session of a user who turned two-step on but hasn't passed it. Turning it on is each user's choice.

## Step 5 — Supabase key → Vercel and local
Dashboard → **Project Settings → API Keys** → copy the **Publishable key** (starts `sb_publishable_`; a legacy
"anon" key works too if legacy keys are still enabled).
- **Vercel** → project `app.mytrakin123` → Settings → Environment Variables → `NEXT_PUBLIC_SUPABASE_ANON_KEY` = that
  key (Production) → **Redeploy** (these variables are baked in at build time).
- **Local:** same value in `apps/web/.env.local`. On 2026-10-13 the key in that file was rejected ("Invalid API key"),
  so local sign-in fails until it is replaced.
- Also confirm on Vercel project `app.mytrakin123`: `NEXT_PUBLIC_SUPABASE_URL` = `https://pcxewovgpnmbpehlqiqg.supabase.co`
  and `NEXT_PUBLIC_API_URL` = `https://trakin-new.vercel.app`; and on project `trakin-new`:
  `WEB_ORIGIN` = `https://www.mytrackin.com`.

## Step 6 — Test it (about 10 minutes)
1. `https://www.mytrackin.com/login` shows **Google** and **Microsoft** (a button for a provider that is off in Supabase
   is hidden, so both appearing proves steps 2–3 took effect).
2. Google → lands in the app (or "no workspace yet" without an invite — expected).
3. Microsoft → same; try a work account and a personal one.
4. Admin/finance account → asked to set up or enter the authenticator code → dashboard.
5. A normal account that added an authenticator app (Account & security) → asked for the code after any sign-in method.
6. *Use a password* → *Forgot password?* → e-mail arrives → link opens `/reset-password` (same browser) → new password
   (12+ characters, letters and numbers) → signed in.
7. Cancel on the Google/Microsoft screen → red "Sign-in was cancelled" message.
8. `/create-account` shows the two buttons.

## Later / housekeeping
- Replace the Microsoft secret before **2028-10-13**: `az ad app credential reset --id 32328f1e-a9a5-43cf-943f-b40f26e82527 --years 2`,
  then paste the new value in Supabase (Step 2).
- Remove the Microsoft app entirely: `az ad app delete --id 32328f1e-a9a5-43cf-943f-b40f26e82527`.
- The old Google/LinkedIn keys in the previous project were empty, so nothing was reusable.
