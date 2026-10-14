"use client";

import { api } from "@/lib/api";
import { Field, formValues, useAction } from "./ui";

export function CompanyForm({ initial, onSaved }: { initial?: any; onSaved: (c: any) => void }) {
  const { run, busy } = useAction();
  return (
    <form className="form" onSubmit={async (e) => {
      e.preventDefault();
      const body = formValues(e.currentTarget);
      const saved = await run(() => initial ? api(`/companies/${initial.id}`, { method: "PATCH", body }) : api("/companies", { body }), "Saved");
      if (saved) onSaved(saved);
    }}>
      <div className="fields">
        <Field label="Legal name" name="name" required defaultValue={initial?.name} full />
        <Field label="Type" name="kind" as="select" options={["client", "prime_vendor", "vendor", "end_client"]} defaultValue={initial?.kind} />
        <Field label="Company domain" name="domain" defaultValue={initial?.domain ?? ""} placeholder="acme.com" />
        <Field label="Business type" name="business_type" defaultValue={initial?.business_type ?? ""} placeholder="LLC / Corporation" />
        <Field label="DBA" name="dba" defaultValue={initial?.dba ?? ""} />
        <Field label="Payment terms" name="default_terms" defaultValue={initial?.default_terms ?? "Net 30"} placeholder="Net 30 / Pay-when-paid" />
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
