"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { supabase } from "@/lib/supabase";
import { useSession } from "@/lib/session";

type Step = "choose" | "email" | "email_code" | "phone" | "phone_code" | "password" | "sso" | "mfa";

export default function LoginPage() {
  return (
    <Suspense>
      <Login />
    </Suspense>
  );
}

function Login() {
  const params = useSearchParams();
  const router = useRouter();
  const { refresh } = useSession();
  const next = params.get("next") || "/";
  const [step, setStep] = useState<Step>(params.get("step") === "mfa" ? "mfa" : params.get("email") ? "email" : "choose");
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [phone, setPhone] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const sb = supabase();

  async function attempt(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  /** After the first factor: ask for the authenticator code if the account has one, then go in. */
  async function finish() {
    const { data } = await sb.auth.mfa.getAuthenticatorAssuranceLevel();
    if (data && data.nextLevel === "aal2" && data.currentLevel !== "aal2") {
      setStep("mfa");
      return;
    }
    await refresh();
    router.replace(next);
  }

  /** Supabase sends the code e-mail; when its mailer is down, say so plainly. */
  function friendlyEmailError(error: Error): Error {
    if (/sending|confirmation email|rate limit|unexpected_failure|over_email|email not confirmed/i.test(error.message)) {
      return new Error("E-mail codes aren't going out right now. If you have a password, use that instead — otherwise ask your administrator to set one for you.");
    }
    return error;
  }

  const sendEmailCode = (e: FormEvent) => {
    e.preventDefault();
    attempt(async () => {
      const { error } = await sb.auth.signInWithOtp({ email, options: { shouldCreateUser: true } });
      if (error) throw friendlyEmailError(error);
      setInfo(`We sent a 6-digit code to ${email}.`);
      setStep("email_code");
    });
  };

  const verifyEmailCode = (code: string) =>
    attempt(async () => {
      const { error } = await sb.auth.verifyOtp({ email, token: code, type: "email" });
      if (error) throw new Error("That code didn't work. Check the latest e-mail, or send a new code.");
      await finish();
    });

  const sendPhoneCode = (e: FormEvent) => {
    e.preventDefault();
    attempt(async () => {
      const normalized = phone.replace(/[^\d+]/g, "");
      // Only numbers already added to an account (Account & security) can sign in by text.
      const { error } = await sb.auth.signInWithOtp({ phone: normalized.startsWith("+") ? normalized : `+1${normalized}`, options: { shouldCreateUser: false } });
      if (error) throw new Error("We couldn't text that number. Sign in with an e-mail code first and add your mobile under Account & security.");
      setInfo("We texted you a 6-digit code.");
      setStep("phone_code");
    });
  };

  const verifyPhoneCode = (code: string) =>
    attempt(async () => {
      const normalized = phone.replace(/[^\d+]/g, "");
      const { error } = await sb.auth.verifyOtp({ phone: normalized.startsWith("+") ? normalized : `+1${normalized}`, token: code, type: "sms" });
      if (error) throw new Error("That code didn't work. Send a new one and try again.");
      await finish();
    });

  const passwordSignIn = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const password = new FormData(e.currentTarget).get("password") as string;
    attempt(async () => {
      const { error } = await sb.auth.signInWithPassword({ email, password });
      if (error) throw new Error("E-mail or password is not right.");
      await finish();
    });
  };

  const ssoSignIn = (e: FormEvent) => {
    e.preventDefault();
    attempt(async () => {
      const domain = email.includes("@") ? email.split("@")[1]! : email;
      const { data, error } = await sb.auth.signInWithSSO({ domain, options: { redirectTo: `${location.origin}/login?next=${encodeURIComponent(next)}` } });
      if (error) throw new Error("Single sign-on isn't set up for this company domain. Use an e-mail code instead.");
      location.href = data.url;
    });
  };

  const oauth = (provider: "google" | "azure") =>
    attempt(async () => {
      const { error } = await sb.auth.signInWithOAuth({
        provider, options: { redirectTo: `${location.origin}/login?next=${encodeURIComponent(next)}`, scopes: provider === "azure" ? "email" : undefined },
      });
      if (error) throw error;
    });

  // Returning from SSO / Google / Microsoft: the session is already in the URL.
  useEffect(() => {
    sb.auth.getSession().then(({ data }) => {
      if (data.session && step === "choose") finish();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="auth">
      <div className="logo" style={{ justifyContent: "center", fontSize: 20 }}><i>mT</i>myTrakIn</div>
      <div className="card">
        {step === "choose" && (
          <>
            <h2>Sign in</h2>
            <p className="muted">Use the e-mail address your company invited.</p>
            <button className="btn pri authbtn" onClick={() => setStep("email")}>E-mail me a code<span>No password needed</span></button>
            <button className="btn authbtn" onClick={() => setStep("sso")}>Company single sign-on (SSO)<span>Okta, Microsoft Entra ID, Google Workspace…</span></button>
            <div className="row mt">
              <button className="btn" style={{ flex: 1 }} onClick={() => oauth("google")}>Google</button>
              <button className="btn" style={{ flex: 1 }} onClick={() => oauth("azure")}>Microsoft</button>
            </div>
            <div className="row mt" style={{ justifyContent: "space-between" }}>
              <a onClick={() => setStep("phone")}>Text me a code</a>
              <a onClick={() => setStep("password")}>Use a password</a>
            </div>
          </>
        )}

        {step === "email" && (
          <form onSubmit={sendEmailCode} className="form">
            <h2>Sign in with an e-mail code</h2>
            <label htmlFor="email">Work or personal e-mail</label>
            <input id="email" className="ctl" type="email" required autoFocus autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <button className="btn pri mt" disabled={busy} style={{ width: "100%" }}>Send code</button>
          </form>
        )}

        {(step === "email_code" || step === "phone_code") && (
          <CodeEntry info={info} busy={busy} onSubmit={step === "email_code" ? verifyEmailCode : verifyPhoneCode}
                     onResend={() => setStep(step === "email_code" ? "email" : "phone")} />
        )}

        {step === "phone" && (
          <form onSubmit={sendPhoneCode} className="form">
            <h2>Sign in with a text message</h2>
            <label htmlFor="phone">Mobile number on your profile</label>
            <input id="phone" className="ctl" type="tel" required autoFocus autoComplete="tel" placeholder="(555) 010-2030" value={phone} onChange={(e) => setPhone(e.target.value)} />
            <button className="btn pri mt" disabled={busy} style={{ width: "100%" }}>Text me a code</button>
            <p className="note">Message and data rates may apply.</p>
          </form>
        )}

        {step === "password" && (
          <form onSubmit={passwordSignIn} className="form">
            <h2>Sign in with a password</h2>
            <label htmlFor="pe">E-mail</label>
            <input id="pe" className="ctl" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <label htmlFor="pw">Password</label>
            <input id="pw" name="password" className="ctl" type="password" required autoComplete="current-password" />
            <button className="btn pri mt" disabled={busy} style={{ width: "100%" }}>Sign in</button>
            <p className="note">Forgot it? Sign in with an e-mail code, then set a new password under Account & security.</p>
          </form>
        )}

        {step === "sso" && (
          <form onSubmit={ssoSignIn} className="form">
            <h2>Company single sign-on</h2>
            <label htmlFor="se">Work e-mail or company domain</label>
            <input id="se" className="ctl" required autoFocus placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} />
            <button className="btn pri mt" disabled={busy} style={{ width: "100%" }}>Continue</button>
          </form>
        )}

        {step === "mfa" && <MfaStep onDone={async () => { await refresh(); router.replace(next); }} />}

        {error && <p className="err" role="alert">{error}</p>}
        {step !== "choose" && step !== "mfa" && <p className="mt"><a onClick={() => { setStep("choose"); setError(null); }}>← Other ways to sign in</a></p>}
      </div>
      <p className="muted" style={{ textAlign: "center" }}>
        New user? <Link href="/create-account">Create an account</Link>
      </p>
      <p className="muted" style={{ textAlign: "center" }}>
        New company? <Link href="/signup">Request a workspace</Link>
      </p>
    </div>
  );
}

function CodeEntry({ info, busy, onSubmit, onResend }: { info: string | null; busy: boolean; onSubmit: (code: string) => void; onResend: () => void }) {
  const [code, setCode] = useState("");
  return (
    <form className="form" onSubmit={(e) => { e.preventDefault(); onSubmit(code); }}>
      <h2>Enter your code</h2>
      {info && <p className="muted">{info}</p>}
      <label htmlFor="code">6-digit code</label>
      <input id="code" className="ctl" inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6} required autoFocus
             value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} style={{ fontSize: 22, letterSpacing: 8, textAlign: "center" }} />
      <button className="btn pri mt" disabled={busy || code.length !== 6} style={{ width: "100%" }}>Sign in</button>
      <p className="note">Didn't get it? Check spam, or <a onClick={onResend}>send a new code</a>.</p>
    </form>
  );
}

/** Two-step verification with an authenticator app (TOTP). Enrolls on first use. */
function MfaStep({ onDone }: { onDone: () => void }) {
  const sb = supabase();
  const [factorId, setFactorId] = useState<string | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const { data } = await sb.auth.mfa.listFactors();
      const verified = data?.totp.find((f) => f.status === "verified");
      if (verified) return setFactorId(verified.id);
      // Remove half-finished enrollments, then start a new one.
      for (const f of data?.all ?? []) if (f.status !== "verified") await sb.auth.mfa.unenroll({ factorId: f.id });
      const { data: enrolled, error } = await sb.auth.mfa.enroll({ factorType: "totp", friendlyName: `Authenticator ${new Date().toISOString().slice(0, 10)}` });
      if (error) return setError(error.message);
      setFactorId(enrolled.id);
      setQr(enrolled.totp.qr_code);
      setSecret(enrolled.totp.secret);
    })();
  }, [sb]);

  const verify = async (e: FormEvent) => {
    e.preventDefault();
    if (!factorId) return;
    setError(null);
    const { error } = await sb.auth.mfa.challengeAndVerify({ factorId, code });
    if (error) return setError("That code didn't match. Use the current code from your authenticator app.");
    onDone();
  };

  return (
    <form className="form" onSubmit={verify}>
      <h2>Two-step verification</h2>
      {qr ? (
        <>
          <p className="muted">Your role handles money, so two-step verification is required. Scan this with Google Authenticator,
            Microsoft Authenticator, 1Password or Authy, then enter the 6-digit code.</p>
          <img src={qr} alt="QR code for your authenticator app" width={180} height={180} style={{ background: "#fff", borderRadius: 8 }} />
          <p className="note">Can't scan? Enter this key: <code>{secret}</code></p>
        </>
      ) : (
        <p className="muted">Enter the 6-digit code from your authenticator app.</p>
      )}
      <label htmlFor="totp">Code</label>
      <input id="totp" className="ctl" inputMode="numeric" autoComplete="one-time-code" maxLength={6} required autoFocus
             value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} style={{ fontSize: 22, letterSpacing: 8, textAlign: "center" }} />
      <button className="btn pri mt" disabled={code.length !== 6} style={{ width: "100%" }}>Verify</button>
      {error && <p className="err" role="alert">{error}</p>}
    </form>
  );
}
