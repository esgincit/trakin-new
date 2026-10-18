"use client";

import type { ReactNode } from "react";
import { supabase } from "@/lib/supabase";
import { useEnabledProviders } from "@/lib/authProviders";

/** Same frame for every sign-in style page: logo, one card, links underneath. */
export function AuthLayout({ children, footer }: { children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="auth">
      <div className="logo" style={{ justifyContent: "center", fontSize: 20 }}><i>mT</i>myTrakIn</div>
      <div className="card">{children}</div>
      {footer}
    </div>
  );
}

/** The password rule used everywhere (matches Account & security): 12+ characters, letters and numbers. */
export const isStrongPassword = (pw: string) => pw.length >= 12 && /[A-Za-z]/.test(pw) && /\d/.test(pw);

/** Turns Supabase's technical sign-in errors into something a person can act on. */
export function friendlyAuthError(error: { message?: string; code?: string } | string | null | undefined): string {
  if (typeof error === "string") return error || "Something went wrong. Please try again.";
  const m = error?.message ?? "";
  const code = error?.code ?? "";
  // Asking for a second code too quickly is not a broken mail server - it is a
  // one-minute cooldown on the address. Say so, with the time it actually needs,
  // instead of telling people to e-mail their administrator.
  if (/over_email_send_rate_limit|over_sms_send_rate_limit/.test(code)
      || /only request this after (\d+) second/i.test(m)) {
    const secs = m.match(/after (\d+) second/i)?.[1];
    return secs
      ? `You asked for a code a moment ago. Wait ${secs} seconds and ask again - only one code can be sent per minute.`
      : "You asked for a code a moment ago. Wait a minute and ask again - only one code can be sent per minute.";
  }
  if (/provider is not enabled|unsupported provider/i.test(m))
    return "That sign-in option isn't switched on yet. Use an e-mail code instead, or ask your administrator.";
  if (/invalid api key/i.test(m))
    return "Sign-in isn't set up correctly on this server (the Supabase key is wrong). Tell your administrator.";
  if (/access_denied/i.test(m)) return "Sign-in was cancelled. Try again or choose another way.";
  if (/redirect/i.test(m) && /not allowed|invalid/i.test(m))
    return "This web address isn't allowed for sign-in yet. Ask your administrator to add it in Supabase.";
  if (/sending|confirmation email|unexpected_failure|over_email|email not confirmed/i.test(m))
    return "We couldn't send the e-mail. Please try again in a minute.";
  return m || "Something went wrong. Please try again.";
}

const GoogleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
    <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z" />
    <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4.1 7.1-10.1 7.1-17.5z" />
    <path fill="#FBBC05" d="M10.5 28.7a14.5 14.5 0 0 1 0-9.4l-7.9-6.1a24 24 0 0 0 0 21.6l7.9-6.1z" />
    <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.5-5.8c-2.1 1.4-4.8 2.3-8.4 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z" />
  </svg>
);

const MicrosoftIcon = () => (
  <svg width="18" height="18" viewBox="0 0 23 23" aria-hidden="true">
    <path fill="#F25022" d="M1 1h10v10H1z" /><path fill="#7FBA00" d="M12 1h10v10H12z" />
    <path fill="#00A4EF" d="M1 12h10v10H1z" /><path fill="#FFB900" d="M12 12h10v10H12z" />
  </svg>
);

/**
 * "Google" and "Microsoft" buttons. A button whose provider is known to be switched off in
 * Supabase is hidden, so nobody clicks into an error; if that can't be checked both show.
 */
export function SocialButtons({ next, verb = "Continue with", onError, onBusy, disabled }: {
  next: string;
  verb?: string;
  onError: (message: string) => void;
  onBusy?: (busy: boolean) => void;
  disabled?: boolean;
}) {
  const enabled = useEnabledProviders();
  const show = { google: enabled ? enabled.google : true, azure: enabled ? enabled.azure : true };
  if (!show.google && !show.azure) return null;

  const go = async (provider: "google" | "azure") => {
    onError("");
    onBusy?.(true);
    // select_account: people with several Google / Microsoft accounts get to choose.
    const { error } = await supabase().auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: `${location.origin}/login?next=${encodeURIComponent(next)}`,
        scopes: provider === "azure" ? "email" : undefined,
        queryParams: { prompt: "select_account" },
      },
    });
    if (error) {
      onBusy?.(false);
      onError(friendlyAuthError(error));
    }
  };

  return (
    <>
      <div className="or"><span>or {verb.toLowerCase()}</span></div>
      <div className="row social">
        {show.google && <button type="button" className="btn" disabled={disabled} onClick={() => go("google")}><GoogleIcon />Google</button>}
        {show.azure && <button type="button" className="btn" disabled={disabled} onClick={() => go("azure")}><MicrosoftIcon />Microsoft</button>}
      </div>
    </>
  );
}
