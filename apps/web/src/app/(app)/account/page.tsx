"use client";

import { useEffect, useState } from "react";
import { PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useSession } from "@/lib/session";
import { supabase } from "@/lib/supabase";

/** Account & security: password, two-step verification, sign-in sessions, preferences and e-mail settings. */
export default function Account() {
  const sb = supabase();
  const { session, me, refresh } = useSession();
  const [factors, setFactors] = useState<any[]>([]);
  const [pw, setPw] = useState({ a: "", b: "" });
  const { run, busy } = useAction();
  const prefs = me?.profile?.preferences ?? {};

  const loadFactors = async () => setFactors((await sb.auth.mfa.listFactors()).data?.all ?? []);
  useEffect(() => { loadFactors(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const savePrefs = async (patch: Record<string, any>) => {
    await run(() => api("/network/me", { method: "PATCH", body: { preferences: { ...prefs, ...patch } } }), "Preference saved");
    await refresh();
    if ("density" in patch) document.body.classList.toggle("compact", patch.density === "compact");
  };

  const strong = pw.a.length >= 12 && /[A-Za-z]/.test(pw.a) && /\d/.test(pw.a);

  return (
    <>
      <PageHead title="Account & security" sub={`Signed in as ${session?.user.email ?? session?.user.phone ?? ""}`} />
      <div className="grid c2">
        <div className="card form">
          <h3>Password</h3>
          <p className="muted">Optional — you can always sign in with an e-mail code. Use at least 12 characters with letters and numbers.</p>
          <label htmlFor="np">New password</label>
          <input id="np" className="ctl" type="password" autoComplete="new-password" value={pw.a} onChange={(e) => setPw({ ...pw, a: e.target.value })} />
          <label htmlFor="np2">Repeat</label>
          <input id="np2" className="ctl" type="password" autoComplete="new-password" value={pw.b} onChange={(e) => setPw({ ...pw, b: e.target.value })} />
          <button className="btn pri mt" disabled={busy || !strong || pw.a !== pw.b} onClick={async () => {
            const ok = await run(async () => { const { error } = await sb.auth.updateUser({ password: pw.a }); if (error) throw error; return true; }, "Password changed");
            if (ok) setPw({ a: "", b: "" });
          }}>Change password</button>
          {pw.a && !strong && <p className="note">Too weak: 12+ characters, letters and numbers.</p>}
        </div>

        <div className="card">
          <PhoneSignIn current={session?.user.phone ?? null} />
          <h3 className="mt">Two-step verification</h3>
          {(() => {
            const on = factors.filter((f) => f.status === "verified");
            if (on.length) return (
              <>
                <p className="muted"><b>On.</b> Signing in asks for a code from your authenticator app.</p>
                {on.map((f) => (
                  <div key={f.id} className="alert">
                    <div style={{ flex: 1 }}><b>{f.friendly_name ?? "Authenticator app"}</b><div className="muted" style={{ fontSize: 12.5 }}>Added {dateTime(f.created_at)}</div></div>
                    <button className="btn sm" disabled={busy} onClick={async () => {
                      await run(async () => { const { error } = await sb.auth.mfa.unenroll({ factorId: f.id }); if (error) throw error; }, "Two-step verification turned off");
                      loadFactors();
                    }}>Turn off</button>
                  </div>
                ))}
              </>
            );
            if (me?.mfa_allowed === false) return <p className="muted">Your company owner hasn&apos;t enabled two-step verification for your account.</p>;
            return (
              <>
                <p className="muted"><b>Off.</b> It&apos;s your choice — turn it on for an extra code at every sign-in.</p>
                <a className="btn mt" href="/login?step=mfa&next=/account">Turn on two-step verification</a>
              </>
            );
          })()}

          <h3 className="mt">Sessions</h3>
          <p className="muted">Signed in since {session?.user.last_sign_in_at ? dateTime(session.user.last_sign_in_at) : "–"}.</p>
          <button className="btn" disabled={busy} onClick={() => run(async () => { const { error } = await sb.auth.signOut({ scope: "others" }); if (error) throw error; }, "Signed out everywhere else")}>Sign out of all other devices</button>
        </div>
      </div>

      <div className="grid c2 mt">
        <div className="card form">
          <h3>Preferences</h3>
          <label htmlFor="dens">Table density</label>
          <select id="dens" className="ctl" defaultValue={prefs.density ?? "comfortable"} onChange={(e) => savePrefs({ density: e.target.value })}>
            <option value="comfortable">Comfortable</option><option value="compact">Compact</option>
          </select>
          <label htmlFor="tz">Time zone</label>
          <select id="tz" className="ctl" defaultValue={prefs.time_zone ?? Intl.DateTimeFormat().resolvedOptions().timeZone} onChange={(e) => savePrefs({ time_zone: e.target.value })}>
            {["America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles", "America/Anchorage", "Pacific/Honolulu", "Asia/Kolkata", "Europe/London"].map((z) => <option key={z}>{z}</option>)}
          </select>
          <p className="note">Theme (auto, dark, light) is the button at the top of every page.</p>
        </div>
        <div className="card">
          <h3>E-mail me about</h3>
          {[["timesheet_reminders", "Timesheet reminders"], ["approvals", "Things waiting for my approval"], ["payments", "Payment status changes"], ["documents", "Documents about to expire"], ["network", "Messages and connection requests"]].map(([k, l]) => (
            <label key={k} className="row" style={{ padding: "6px 0" }}>
              <input type="checkbox" className="toggle" defaultChecked={prefs[`email_${k}`] !== false} onChange={(e) => savePrefs({ [`email_${k}`]: e.target.checked })} /> {l}
            </label>
          ))}
          <p className="note">Legal and compliance notices (e-signature requests, I-9 and work-authorization deadlines) are always sent.</p>
        </div>
      </div>
    </>
  );
}

/** Adds a verified mobile number so the person can also sign in with a text-message code. */
function PhoneSignIn({ current }: { current: string | null }) {
  const sb = supabase();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const { run, busy } = useAction();
  const e164 = (v: string) => { const d = v.replace(/[^\d+]/g, ""); return d.startsWith("+") ? d : `+1${d}`; };
  return (
    <div className="form">
      <h3>Text-message sign-in</h3>
      <p className="muted">{current ? `Mobile on your account: +${current}` : "Add your mobile to sign in with a text-message code."}</p>
      {!sent ? (
        <div className="row">
          <input className="ctl" type="tel" placeholder="(555) 010-2030" value={phone} onChange={(e) => setPhone(e.target.value)} aria-label="Mobile number" />
          <button className="btn" disabled={busy || phone.length < 7} onClick={async () => {
            const ok = await run(async () => { const { error } = await sb.auth.updateUser({ phone: e164(phone) }); if (error) throw error; return true; }, "Code sent by text");
            if (ok) setSent(true);
          }}>{current ? "Change" : "Add"}</button>
        </div>
      ) : (
        <div className="row">
          <input className="ctl" inputMode="numeric" maxLength={6} placeholder="6-digit code" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} aria-label="Code" />
          <button className="btn pri" disabled={busy || code.length !== 6} onClick={async () => {
            const ok = await run(async () => { const { error } = await sb.auth.verifyOtp({ phone: e164(phone), token: code, type: "phone_change" }); if (error) throw error; return true; }, "Mobile number verified");
            if (ok) { setSent(false); setCode(""); }
          }}>Verify</button>
        </div>
      )}
    </div>
  );
}
