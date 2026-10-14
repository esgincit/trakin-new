"use client";

import { useRef, useState } from "react";
import { Chip, Field, formValues, Modal, useAction } from "./ui";
import { api } from "@/lib/api";
import { allows, useSession } from "@/lib/session";

/** Company onboarding: details → W-9 upload + extraction → tax review → verify & activate.
 *  Each step saves to the server, so closing and reopening loses nothing already done. */
export function CompanyWizard({ onClose, onDone }: { onClose: () => void; onDone: (c: any) => void }) {
  const { workspace } = useSession();
  const { run, busy } = useAction();
  const [step, setStep] = useState(1);
  const [company, setCompany] = useState<any>(null);
  const [extraction, setExtraction] = useState<any>(null);
  const [verify, setVerify] = useState<any>(null);
  const w9file = useRef<HTMLInputElement>(null);
  const canDecideW9 = allows(workspace, "finance", "legal");

  const create = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const c = await run(() => api("/companies", { body: formValues(e.currentTarget) }), "Company drafted — Business ID assigned");
    if (c) { setCompany(c); setStep(2); }
  };

  const uploadW9 = async (file?: File) => {
    if (!file || !company) return;
    const form = new FormData();
    form.set("file", file);
    const r = await run(() => api(`/companies/${company.id}/w9`, { form }), "W-9 uploaded — review the extracted details");
    if (r) { setExtraction(r.extraction); setStep(3); }
  };

  const saveTax = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const r = await run(() => api(`/companies/${company.id}/tax`, { method: "PATCH", body: formValues(e.currentTarget) }), "Tax details saved");
    if (r) { setCompany(r); setStep(4); check(); }
  };

  const check = async () => {
    const r = await run(() => api(`/companies/${company.id}/verify`, { method: "POST", body: {} }));
    if (r) setVerify(r);
  };

  const decide = async (decision: "verified" | "rejected") => {
    const note = decision === "rejected" ? prompt("What's wrong with this W-9?") : undefined;
    if (decision === "rejected" && !note) return;
    if (await run(() => api(`/companies/${company.id}/w9/decision`, { body: { decision, note } }), decision === "verified" ? "W-9 verified" : "W-9 sent back")) check();
  };

  const activate = async () => {
    const r = await run(() => api(`/companies/${company.id}/activate`, { method: "POST", body: {} }), "Company activated");
    if (r) onDone({ ...company, status: "active", business_code: r.business_code });
  };

  return (
    <Modal title={`New company — step ${step} of 4`} onClose={onClose}>
      <div className="steps" style={{ marginBottom: 12 }}>
        {["Details", "W-9 upload", "Tax review", "Verify & activate"].map((s, i) => (
          <div key={s} className={`step ${i + 1 < step ? "done" : i + 1 === step ? "cur" : ""}`}>
            <span className="dot">{i + 1 < step ? "✓" : i + 1}</span><div><b style={{ fontSize: 12.5 }}>{s}</b></div>
          </div>
        ))}
      </div>

      {step === 1 && (
        <form className="form" onSubmit={create}>
          <div className="fields">
            <Field label="Legal name" name="name" required full />
            <Field label="Type" name="kind" as="select" options={["client", "prime_vendor", "vendor", "end_client"]} defaultValue="vendor" />
            <Field label="Company domain" name="domain" required placeholder="acme.com" />
            <Field label="Business type" name="business_type" placeholder="LLC / Corporation / …" />
            <Field label="DBA (if different)" name="dba" />
            <Field label="Business address" name="address" required full />
            <Field label="State" name="state" maxLength={2} placeholder="TX" />
            <Field label="Contact name" name="contact_name" />
            <Field label="Contact e-mail (must be on the domain)" name="contact_email" type="email" required />
            <Field label="Contact phone" name="contact_phone" />
            <Field label="Payment terms" name="default_terms" defaultValue="Net 30" />
          </div>
          <button className="btn pri mt" disabled={busy}>Create draft & continue</button>
        </form>
      )}

      {step === 2 && company && (
        <>
          <p className="muted">Business ID <b>{company.business_code}</b> is reserved. Now upload the signed W-9 — details are extracted automatically (scanned pages use OCR when available, otherwise type them in the next step).</p>
          <input ref={w9file} type="file" accept="application/pdf,image/jpeg,image/png,image/webp" hidden
                 onChange={(e) => uploadW9(e.target.files?.[0])} />
          <div className="row">
            <button className="btn pri" disabled={busy} onClick={() => w9file.current?.click()}>Upload W-9</button>
            <button className="btn" disabled={busy} onClick={() => setStep(3)}>Skip — enter manually</button>
          </div>
        </>
      )}

      {step === 3 && company && (
        <form className="form" onSubmit={saveTax}>
          {extraction && (
            <p className="muted">Extracted via {extraction.engine === "ocr" ? "OCR" : "document text"}{extraction.note ? ` — ${extraction.note}` : ". Check every field."}</p>
          )}
          <div className="fields">
            {extraction?.legal_name && (
            <p className="muted" style={{ gridColumn: "1 / -1" }}>W-9 line 1 (legal name): <b>{extraction.legal_name}</b> — correct the company name if it differs.</p>
          )}
          <Field label="Business name / DBA (W-9 line 2)" name="dba" defaultValue={extraction?.dba ?? company.dba ?? ""} full />
            <Field label="Federal tax classification" name="tax_classification" defaultValue={extraction?.tax_classification ?? ""} placeholder="S Corporation / LLC / …" />
            <Field label="TIN type" name="tin_type" as="select" defaultValue={extraction?.tin_type ?? "ein"} options={[["ein", "EIN"], ["ssn", "SSN"]]} />
            <Field label="TIN" name="tin" defaultValue={extraction?.tin ?? ""} placeholder="12-3456789" required />
            <Field label="Tax address" name="tax_address" defaultValue={[extraction?.address, extraction?.city, extraction?.state, extraction?.zip].filter(Boolean).join(", ")} full />
            <Field label="EIN (company record)" name="ein" defaultValue={company.ein ?? extraction?.tin ?? ""} />
          </div>
          <div className="row mt">
            <button className="btn" disabled={busy} onClick={() => setStep(2)}>Back</button>
            <button className="btn pri" disabled={busy}>Save & continue</button>
          </div>
        </form>
      )}

      {step === 4 && company && (
        <>
          {!verify && <p className="muted">Running verification…</p>}
          {verify && <CheckList checks={verify.checks} blockers={verify.blockers} />}
          {canDecideW9 && <p className="mt"><button className="btn sm" disabled={busy} onClick={() => decide("verified")}>Mark W-9 verified</button></p>}
          <div className="row mt">
            <button className="btn" disabled={busy} onClick={() => setStep(3)}>Back</button>
            {verify && !verify.blockers.length ? (
              <button className="btn pri" disabled={busy} onClick={activate}>Activate {company.business_code}</button>
            ) : (
              <button className="btn" disabled={busy} onClick={check}>Re-check</button>
            )}
          </div>
          {verify && !!verify.blockers.length && (
            <p className="note">Activation stays locked until every check passes — including staff W-9 approval{canDecideW9 ? " (use the button above)" : " (ask finance or legal)"}.</p>
          )}
        </>
      )}
    </Modal>
  );
}

export function CheckList({ checks, blockers }: { checks: Record<string, any>; blockers: string[] }) {
  const rows: [string, string][] = [
    ["Required details", "required_fields"], ["Domain", "domain"], ["Mail server", "mx"],
    ["W-9", "w9"], ["TIN match", "tin_match"], ["Owner", "owner"],
  ];
  return (
    <>
      {rows.map(([label, key]) => checks[key] && (
        <div key={key} className="alert">
          <Chip status={checks[key].status === "pass" ? "verified" : checks[key].status === "warn" ? "submitted" : "rejected"} />
          <div><b>{label}</b><div className="muted" style={{ fontSize: 12.5 }}>{checks[key].detail}</div></div>
        </div>
      ))}
      {!!blockers.length && <p className="err">Still needed: {blockers.join("; ")}</p>}
    </>
  );
}
