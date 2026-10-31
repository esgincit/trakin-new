"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Field, formValues, NetTerms, useAction } from "./ui";

const ROLE_OPTIONS: [string, string][] = [["client", "Client"], ["prime_vendor", "Prime vendor"], ["vendor", "Vendor"], ["end_client", "End client"]];

export function CompanyForm({ initial, onSaved }: { initial?: any; onSaved: (c: any) => void }) {
  const { run, busy } = useAction();
  const [kinds, setKinds] = useState<string[]>(initial?.kinds ?? (initial?.kind ? [initial.kind] : ["client"]));
  return (
    <form className="form" onSubmit={async (e) => {
      e.preventDefault();
      const body = { ...formValues(e.currentTarget), kinds, kind: kinds[0] };
      const saved = await run(() => initial ? api(`/companies/${initial.id}`, { method: "PATCH", body }) : api("/companies", { body }), "Saved");
      if (saved) onSaved(saved);
    }}>
      <div className="fields">
        <Field label="Legal name" name="name" required defaultValue={initial?.name} full />
        <div style={{ gridColumn: "1 / -1" }}>
          <p className="muted" style={{ margin: "0 0 6px" }}>Roles — tick all that apply (first ticked is primary).</p>
          <div className="checkgroup" role="group" aria-label="Business roles">
            {ROLE_OPTIONS.map(([v, label]) => (
              <label key={v} className="check">
                <input type="checkbox" checked={kinds.includes(v)}
                  onChange={() => setKinds(kinds.includes(v) ? kinds.filter((x) => x !== v) : [...kinds, v])} />
                <span>{label}</span>
              </label>
            ))}
          </div>
        </div>
        <Field label="Company domain" name="domain" defaultValue={initial?.domain ?? ""} placeholder="acme.com" />
        <Field label="Business type" name="business_type" defaultValue={initial?.business_type ?? ""} placeholder="LLC / Corporation" />
        <Field label="DBA" name="dba" defaultValue={initial?.dba ?? ""} />
        <NetTerms label="Payment terms" name="default_terms" defaultValue={initial?.default_terms ?? "Net 30"} />
        <Field label="EIN" name="ein" defaultValue={initial?.ein ?? ""} placeholder="12-3456789" />
        <Field label="State" name="state" maxLength={2} defaultValue={initial?.state ?? ""} placeholder="TX" />
        <Field label="Contact name" name="contact_name" defaultValue={initial?.contact_name ?? ""} />
        <Field label="Contact e-mail (invoices and reminders)" name="contact_email" type="email" defaultValue={initial?.contact_email ?? ""} />
        <Field label="Contact phone" name="contact_phone" defaultValue={initial?.contact_phone ?? ""} />
        <Field label="Address" name="address" defaultValue={initial?.address ?? ""} />
        <Field label="Notes" name="notes" as="textarea" defaultValue={initial?.notes ?? ""} full />
      </div>
      <button className="btn pri mt" disabled={busy}>Save</button>
    </form>
  );
}
