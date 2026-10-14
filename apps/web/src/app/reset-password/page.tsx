"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { AuthLayout, friendlyAuthError, isStrongPassword } from "@/components/auth";
import { supabase } from "@/lib/supabase";

type State = "checking" | "ready" | "invalid";

/** Landing page of the "Forgot password?" e-mail link: choose a new password, then continue to the app. */
export default function ResetPassword() {
  const router = useRouter();
  const [state, setState] = useState<State>("checking");
  const [pw, setPw] = useState({ a: "", b: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const sb = supabase();
    // The link in the e-mail signs the person in; getSession waits until Supabase has read it from the URL.
    sb.auth.getSession().then(({ data }) => setState(data.session ? "ready" : "invalid"));
    const { data: sub } = sb.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY") setState("ready");
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  const strong = isStrongPassword(pw.a);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!strong || pw.a !== pw.b) return;
    setBusy(true);
    setError(null);
    const sb = supabase();
    const { error } = await sb.auth.updateUser({ password: pw.a });
    if (error) {
      setBusy(false);
      setError(/aal2|mfa/i.test(error.message)
        ? "Your account has two-step verification. Enter your authenticator code first, then set the new password."
        : friendlyAuthError(error));
      return;
    }
    // Same rule as every other sign-in: an account with an authenticator app must prove it before entering.
    const { data } = await sb.auth.mfa.getAuthenticatorAssuranceLevel();
    const needsMfa = data && data.nextLevel === "aal2" && data.currentLevel !== "aal2";
    router.replace(needsMfa ? "/login?step=mfa&next=%2F" : "/");
  };

  return (
    <AuthLayout footer={<p className="muted" style={{ textAlign: "center" }}><Link href="/login">Back to sign in</Link></p>}>
      {state === "checking" && <p className="muted">Checking your link…</p>}

      {state === "invalid" && (
        <>
          <h2>This link has expired</h2>
          <p className="muted">Reset links work once, expire after an hour, and must be opened in the same browser you asked
            from. Ask for a new one on the sign-in page (choose “Use a password”, then “Forgot password?”).</p>
          <Link className="btn pri mt" href="/login">Back to sign in</Link>
        </>
      )}

      {state === "ready" && (
        <form className="form" onSubmit={save}>
          <h2>Choose a new password</h2>
          <p className="muted">Use at least 12 characters with letters and numbers.</p>
          <label htmlFor="np">New password</label>
          <input id="np" className="ctl" type="password" autoComplete="new-password" required autoFocus
                 value={pw.a} onChange={(e) => setPw({ ...pw, a: e.target.value })} />
          <label htmlFor="np2">Repeat the password</label>
          <input id="np2" className="ctl" type="password" autoComplete="new-password" required
                 value={pw.b} onChange={(e) => setPw({ ...pw, b: e.target.value })} />
          {pw.a && !strong && <p className="note">Too weak: 12+ characters, letters and numbers.</p>}
          {pw.b && pw.a !== pw.b && <p className="note">The two passwords don't match.</p>}
          <button className="btn pri mt" disabled={busy || !strong || pw.a !== pw.b} style={{ width: "100%" }}>Save password and continue</button>
          {error && <p className="err" role="alert">{error}</p>}
          {error && /authenticator/.test(error) && <p className="note"><Link href="/login?step=mfa&next=%2Freset-password">Enter authenticator code</Link></p>}
        </form>
      )}
    </AuthLayout>
  );
}
