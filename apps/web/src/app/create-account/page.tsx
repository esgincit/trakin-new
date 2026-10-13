"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Field, formValues } from "@/components/ui";
import { useSession } from "@/lib/session";
import { supabase } from "@/lib/supabase";

/** Self-service user signup: name, e-mail, password. Workspace access still needs an invite. */
export default function CreateAccount() {
  const router = useRouter();
  const { refresh } = useSession();
  const [state, setState] = useState<"form" | "confirm" | "done">("form");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  /** Supabase sends the confirmation e-mail; when its mailer is down, say so plainly. */
  function friendlyError(message: string): string {
    return /sending|confirmation email|rate limit|unexpected_failure|over_email/i.test(message)
      ? "E-mail confirmation isn't going out right now, so this didn't go through and no account was made. Ask your administrator to create your account — they can do it without e-mail."
      : message;
  }

  const resend = async () => {
    setBusy(true); setError(null);
    try {
      const { error } = await supabase().auth.resend({ type: "signup", email });
      if (error) throw error;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (state === "confirm") {
    return <div className="auth"><div className="card">
      <h2>Check your inbox</h2>
      <p className="muted">We sent a confirmation link to {email}. Open it to finish creating your account,
        then sign in. The link expires in 24 hours.</p>
      <p className="muted">Didn't get it? Check spam, then <a onClick={resend}>send it again</a>.</p>
      {error && <p className="err">{error}</p>}
      <Link href="/login" className="btn mt">Back to sign in</Link>
    </div></div>;
  }

  return (
    <div className="auth">
      <div className="logo" style={{ justifyContent: "center", fontSize: 20 }}><i>mT</i>myTrakIn</div>
      <div className="card">
        <h2>Create your account</h2>
        <p className="muted">One account works across every workspace that invites you.
          Opening a workspace needs an invite from its administrator.</p>
        <form className="form" onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true); setError(null);
          const v = formValues(e.currentTarget);
          if ((v.password ?? "").length < 8) {
            setError("Use a password of at least 8 characters.");
            setBusy(false);
            return;
          }
          try {
            const { data, error } = await supabase().auth.signUp({
              email: v.email!,
              password: v.password!,
              options: {
                data: { full_name: v.full_name ?? "" },
                emailRedirectTo: `${location.origin}/login?email=${encodeURIComponent(v.email!)}`,
              },
            });
            if (error) throw error;
            setEmail(v.email!);
            if (data.session) {
              await refresh();
              setState("done");
              router.replace("/");
            } else {
              setState("confirm");
            }
          } catch (err) {
            const message = friendlyError((err as Error).message);
            setError(/already registered|already exists/i.test((err as Error).message)
              ? "That e-mail already has an account. Sign in instead — we filled it in for you."
              : message);
            if (/already registered|already exists/i.test(message)) setEmail(v.email!);
          } finally {
            setBusy(false);
          }
        }}>
          <Field label="Your name" name="full_name" required autoComplete="name" full />
          <Field label="E-mail" name="email" type="email" required autoComplete="email" full />
          <Field label="Password" name="password" type="password" required autoComplete="new-password"
                 minLength={8} placeholder="At least 8 characters" full />
          <button className="btn pri mt" disabled={busy} style={{ width: "100%" }}>Create account</button>
          {error && (
            <p className="err" role="alert">{error}{email && /already has an account/.test(error) && (
              <> <Link href={`/login?email=${encodeURIComponent(email)}`}>Sign in</Link></>
            )}</p>
          )}
        </form>
      </div>
      <p className="muted" style={{ textAlign: "center" }}>
        Already have an account? <Link href="/login">Sign in</Link>
      </p>
    </div>
  );
}
