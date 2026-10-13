"use client";

import Link from "next/link";
import { useState } from "react";
import { Field, formValues } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

/** A staffing company asks for its own myTrakIn workspace. The platform owner reviews and approves it. */
export default function Signup() {
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (sent) {
    return <div className="auth"><div className="card"><h2>Thanks — request received</h2>
      <p className="muted">We verify every company before opening a workspace, usually within one business day. You'll get an e-mail with a sign-in link.</p>
      <Link href="/login" className="btn">Back to sign in</Link></div></div>;
  }
  return (
    <div className="auth" style={{ maxWidth: 620 }}>
      <div className="logo" style={{ justifyContent: "center", fontSize: 20 }}><i>mT</i>myTrakIn</div>
      <div className="card">
        <h2>Request a workspace for your company</h2>
        <p className="muted">For staffing companies that bill clients and pay vendors, 1099 contractors and W-2 employees.</p>
        <form className="form" onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true); setError(null);
          const v: any = formValues(e.currentTarget);
          v.seats = Number(v.seats || 5);
          try { await api("/public/signups", { body: v, auth: false }); setSent(true); }
          catch (err) { setError((err as ApiError).message); }
          finally { setBusy(false); }
        }}>
          <div className="fields">
            <Field label="Company legal name" name="company" required full />
            <Field label="Your name" name="contact_name" required />
            <Field label="Work e-mail" name="email" type="email" required />
            <Field label="Phone" name="phone" type="tel" />
            <Field label="State" name="state" maxLength={2} placeholder="TX" />
            <Field label="EIN" name="ein" placeholder="12-3456789" />
            <Field label="Expected users" name="seats" type="number" min={1} defaultValue={5} />
            <Field label="Plan" name="plan" as="select" options={[["starter", "Starter"], ["growth", "Growth"], ["enterprise", "Enterprise"]]} defaultValue="growth" full />
          </div>
          <button className="btn pri mt" disabled={busy} style={{ width: "100%" }}>Send request</button>
          {error && <p className="err">{error}</p>}
        </form>
      </div>
      <p className="muted" style={{ textAlign: "center" }}>
        Just need a user account? <Link href="/create-account">Create one</Link>
      </p>
    </div>
  );
}
