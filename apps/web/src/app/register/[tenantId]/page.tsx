"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Field } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

const KINDS = [
  { key: "client", title: "Client", text: "We'll bill you for consultants' work" },
  { key: "vendor", title: "Vendor (C2C)", text: "You supply consultants and bill us" },
  { key: "1099", title: "1099 contractor", text: "You work for us as an independent contractor" },
  { key: "consultant", title: "Consultant", text: "You're joining as an employee" },
];

/** A company's public registration page: vendors, clients and contractors register; staff approve. */
export default function Register() {
  const { tenantId } = useParams<{ tenantId: string }>();
  const [tenant, setTenant] = useState<any>(null);
  const [kind, setKind] = useState("vendor");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api(`/public/workspaces/${tenantId}`, { auth: false }).then(setTenant).catch((e: ApiError) => setError(e.message));
  }, [tenantId]);

  if (done) return <div className="auth"><div className="card"><h2>Registration received</h2><p className="muted">{tenant?.name} reviews new registrations within two business days and will e-mail you.</p></div></div>;

  return (
    <div className="auth" style={{ maxWidth: 640 }}>
      <div className="logo" style={{ justifyContent: "center", fontSize: 20 }}><i>mT</i>myTrakIn</div>
      <div className="card">
        <h2>Register with {tenant?.name ?? "…"}</h2>
        <div className="choice mt">
          {KINDS.map((k) => <button key={k.key} type="button" className={kind === k.key ? "on" : ""} onClick={() => setKind(k.key)}><b>{k.title}</b><small>{k.text}</small></button>)}
        </div>
        <form className="form" onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true); setError(null);
          const form = new FormData(e.currentTarget);
          form.set("kind", kind);
          for (const [k, v] of [...form.entries()]) if (v === "" || (v instanceof File && !v.name)) form.delete(k);
          try { await api(`/public/workspaces/${tenantId}/registrations`, { form, auth: false }); setDone(true); }
          catch (err) { setError((err as ApiError).message); }
          finally { setBusy(false); }
        }}>
          <div className="fields">
            <Field label={kind === "consultant" || kind === "1099" ? "Full legal name or business name" : "Company legal name"} name="name" required full />
            <Field label="Contact person" name="contact" required />
            <Field label="E-mail" name="email" type="email" required />
            <Field label="Phone" name="phone" type="tel" />
            <Field label="State" name="state" maxLength={2} />
            {kind !== "consultant" && <Field label="EIN" name="ein" placeholder="12-3456789" />}
          </div>
          <label htmlFor="files">Documents (W-9, certificate of incorporation, insurance certificate…)</label>
          <input id="files" name="files" type="file" multiple className="ctl" accept=".pdf,.png,.jpg,.jpeg" />
          <button className="btn pri mt" disabled={busy || !tenant} style={{ width: "100%" }}>Submit registration</button>
          {error && <p className="err">{error}</p>}
        </form>
      </div>
    </div>
  );
}
