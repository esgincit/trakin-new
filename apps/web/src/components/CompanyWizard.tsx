"use client";

import { useRef, useState } from "react";
import { Chip, Field, formValues, Modal, useAction } from "./ui";
import { api, ApiError } from "@/lib/api";

type Country = "US" | "IN";

/** Country-first business creation.
 *  US: W-9 upload (parsed + validated) → domain/e-mail/DBA → OTP → authorize → created.
 *  IN: manual details + mandatory MOA → domain/e-mail/DBA → OTP → authorize → created.
 *  Nothing is created until every gate passes; the creator becomes Super Admin. */
export function CompanyWizard({ onClose, onDone }: { onClose: () => void; onDone: (c: any) => void }) {
  const { run, busy } = useAction();
  const [country, setCountry] = useState<Country | null>(null);
  const [session, setSession] = useState<any>(null);
  const [step, setStep] = useState(1);
  const [parsed, setParsed] = useState<any>(null);
  const [otpSent, setOtpSent] = useState(false);
  const [authorized, setAuthorized] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const w9file = useRef<HTMLInputElement>(null);
  const moafile = useRef<HTMLInputElement>(null);

  const start = async (c: Country) => {
    setError(null);
    const s = await run(() => api("/onboarding/sessions", { body: { country: c } }));
    if (s) { setCountry(c); setSession(s); setStep(1); }
  };

  const fail = (e: unknown) => setError((e as ApiError).message);

  const uploadW9 = async (file?: File) => {
    if (!file || !session) return;
    setError(null);
    const form = new FormData();
    form.set("file", file);
    try {
      const r = await api(`/onboarding/sessions/${session.id}/w9`, { form });
      setParsed(r.parsed);
    } catch (e) { fail(e); }
  };

  const uploadMoa = async (file?: File) => {
    if (!file || !session) return;
    setError(null);
    const form = new FormData();
    form.set("file", file);
    try {
      await api(`/onboarding/sessions/${session.id}/moa`, { form });
      setSession({ ...session, has_moa: true });
    } catch (e) { fail(e); }
  };

  const saveDetails = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    try {
      const s = await api(`/onboarding/sessions/${session.id}`, { method: "PATCH", body: formValues(e.currentTarget) });
      setSession(s);
      setStep(3);
    } catch (e) { fail(e); }
  };

  const sendCode = async () => {
    setError(null);
    try {
      await api(`/onboarding/sessions/${session.id}/email-code`, { method: "POST", body: {} });
      setOtpSent(true);
    } catch (e) { fail(e); }
  };

  const verifyCode = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    const code = new FormData(e.currentTarget).get("code") as string;
    try {
      await api(`/onboarding/sessions/${session.id}/email-verify`, { body: { code } });
      setSession({ ...session, email_verified: true });
    } catch (e) { fail(e); }
  };

  const create = async () => {
    setError(null);
    try {
      const c = await api(`/onboarding/sessions/${session.id}/complete`, { body: { authorized } }, );
      onDone(c);
    } catch (e) { fail(e); }
  };

  if (!country || !session) {
    return (
      <Modal title="New company" onClose={onClose}>
        <p className="muted">Where is the business registered? Fields and checks differ by country.</p>
        <div className="row mt">
          <button className="btn pri" disabled={busy} style={{ flex: 1 }} onClick={() => start("US")}>United States<div className="muted" style={{ fontSize: 12 }}>W-9 + EIN</div></button>
          <button className="btn pri" disabled={busy} style={{ flex: 1 }} onClick={() => start("IN")}>India<div className="muted" style={{ fontSize: 12 }}>MOA + CIN</div></button>
        </div>
      </Modal>
    );
  }

  const steps = country === "US" ? ["W-9 upload", "Company details", "E-mail verification", "Authorize & create"] : ["Details & MOA", "Company details", "E-mail verification", "Authorize & create"];

  return (
    <Modal title={`New ${country === "US" ? "US" : "Indian"} company — step ${step} of 4`} onClose={onClose}>
      <div className="steps" style={{ marginBottom: 12 }}>
        {steps.map((s, i) => (
          <div key={s} className={`step ${i + 1 < step ? "done" : i + 1 === step ? "cur" : ""}`}>
            <span className="dot">{i + 1 < step ? "✓" : i + 1}</span><div><b style={{ fontSize: 12.5 }}>{s}</b></div>
          </div>
        ))}
      </div>
      {error && <p className="err" role="alert">{error}</p>}

      {step === 1 && country === "US" && !parsed && (
        <>
          <p className="muted">First, the signed W-9 (PDF or photo). Legal name, business type, EIN and address are read automatically and the EIN is checked for duplicates.</p>
          <input ref={w9file} type="file" accept="application/pdf,image/jpeg,image/png,image/webp" hidden onChange={(e) => uploadW9(e.target.files?.[0])} />
          <button className="btn pri mt" disabled={busy} onClick={() => w9file.current?.click()}>Upload W-9</button>
        </>
      )}

      {step === 1 && country === "US" && parsed && (
        <form className="form" onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          try {
            const s = await api(`/onboarding/sessions/${session.id}`, { method: "PATCH", body: { kind: (formValues(e.currentTarget) as any).kind, ...parsed } });
            setSession(s); setStep(2);
          } catch (e) { fail(e); }
        }}>
          <p className="muted">Read from the W-9{parsed.engine === "ocr" ? " (scan)" : parsed.engine === "form-fields" ? " (form fields)" : ""} — correct anything misread.</p>
          <div className="fields">
            <Field label="Legal name" name="legal_name" required defaultValue={parsed.legal_name ?? ""} full />
            <Field label="Business type" name="business_type" defaultValue={parsed.tax_classification ?? ""} />
            <Field label="EIN" name="ein" required defaultValue={parsed.tin ?? ""} />
            <Field label="Address" name="address" defaultValue={parsed.address ?? ""} full />
            <Field label="City" name="city" defaultValue={parsed.city ?? ""} />
            <Field label="State" name="state" defaultValue={parsed.state ?? ""} maxLength={2} />
            <Field label="ZIP" name="zip" defaultValue={parsed.zip ?? ""} />
            <Field label="Business role" name="kind" as="select" required options={[["vendor", "Vendor — we pay them"], ["client", "Client — we bill them"], ["prime_vendor", "Prime vendor"], ["end_client", "End client"]]} defaultValue="vendor" full />
          </div>
          <div className="row mt">
            <button className="btn" disabled={busy} onClick={() => setParsed(null)}>Re-upload</button>
            <button className="btn pri" disabled={busy}>Confirm & continue</button>
          </div>
        </form>
      )}

      {step === 1 && country === "IN" && (
        <form className="form" onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          const v: any = formValues(e.currentTarget);
          try {
            const s = await api(`/onboarding/sessions/${session.id}`, { method: "PATCH", body: { ...v, kind: v.kind } });
            setSession(s);
            if (!s.details?.cin || !s.details?.legal_name) return;
            setStep(2);
          } catch (e) { fail(e); }
        }}>
          <p className="muted">Enter the business details as per the MCA records, and attach the Memorandum of Association (mandatory, stored as-is in Phase 1).</p>
          <div className="fields">
            <Field label="Legal name (as per MCA)" name="legal_name" required full />
            <Field label="CIN" name="cin" required placeholder="L12345MH2020PLC123456" full />
            <Field label="Street address" name="street" required full />
            <Field label="City" name="city" required />
            <Field label="State" name="state" required />
            <Field label="PIN code" name="pin" required placeholder="400001" />
            <Field label="Business role" name="kind" as="select" required options={[["vendor", "Vendor — we pay them"], ["client", "Client — we bill them"], ["prime_vendor", "Prime vendor"], ["end_client", "End client"]]} defaultValue="vendor" full />
          </div>
          <input ref={moafile} type="file" accept="application/pdf,image/jpeg,image/png,image/webp" hidden onChange={(e) => uploadMoa(e.target.files?.[0])} />
          <div className="row mt">
            <button type="button" className="btn" disabled={busy} onClick={() => moafile.current?.click()}>
              {session.has_moa ? "MOA attached ✓ — replace" : "Attach MOA (required)"}
            </button>
            <button className="btn pri" disabled={busy || !session.has_moa}>Save & continue</button>
          </div>
          {!session.has_moa && <p className="note">Attach the MOA to continue.</p>}
        </form>
      )}

      {step === 2 && (
        <form className="form" onSubmit={saveDetails}>
          <div className="fields">
            {country === "IN" && <p className="muted" style={{ gridColumn: "1 / -1" }}>CIN verified{session.details?.cin ? ` (${session.details.cin})` : ""}. Now the online identity.</p>}
            <Field label="Business role" name="kind" as="select" required options={[["vendor", "Vendor"], ["client", "Client"], ["prime_vendor", "Prime vendor"], ["end_client", "End client"]]} defaultValue={session.details?.kind ?? "vendor"} full />
            <Field label="Company domain" name="domain" required placeholder={country === "US" ? "acme.com" : "acme.in"} />
            <Field label="Company e-mail" name="company_email" type="email" required defaultValue={session.company_email ?? ""} />
            <Field label="DBA (if different)" name="dba" defaultValue={session.details?.dba ?? ""} full />
            <Field label="Contact person" name="contact_name" />
            <Field label="Contact phone" name="contact_phone" />
          </div>
          <div className="row mt">
            <button className="btn" disabled={busy} onClick={() => setStep(1)}>Back</button>
            <button className="btn pri" disabled={busy}>Save & continue</button>
          </div>
        </form>
      )}

      {step === 3 && (
        <>
          <p className="muted">We prove the e-mail belongs to the business. {session.email_verified ? "Verified ✓" : "Send a 6-digit code, then enter it."}</p>
          {!session.email_verified && (
            <>
              {!otpSent
                ? <button className="btn pri mt" disabled={busy} onClick={sendCode}>Send verification code</button>
                : <form className="form mt" onSubmit={verifyCode}>
                    <Field label="6-digit code" name="code" required inputMode="numeric" maxLength={6} autoFocus />
                    <div className="row mt">
                      <button className="btn pri" disabled={busy}>Verify e-mail</button>
                      <button type="button" className="btn" disabled={busy} onClick={sendCode}>Send again</button>
                    </div>
                  </form>}
            </>
          )}
          <div className="row mt">
            <button className="btn" disabled={busy} onClick={() => setStep(2)}>Back</button>
            {session.email_verified && <button className="btn pri" disabled={busy} onClick={() => setStep(4)}>Continue</button>}
          </div>
        </>
      )}

      {step === 4 && (
        <>
          <div className="alert"><Chip status="ok" /><div><b>Ready to create</b><div className="muted" style={{ fontSize: 12.5 }}>
            {country === "US" ? "W-9 parsed, EIN unique" : "Details entered, CIN unique, MOA attached"} · e-mail verified · {session.details?.domain} · {session.company_email}
          </div></div></div>
          <label className="row mt" style={{ alignItems: "flex-start", gap: 8 }}>
            <input type="checkbox" checked={authorized} onChange={(e) => setAuthorized(e.target.checked)} style={{ marginTop: 4 }} />
            <span>I confirm I am authorized to register this business on myTrakIn, and the details above are true and complete.</span>
          </label>
          <div className="row mt">
            <button className="btn" disabled={busy} onClick={() => setStep(3)}>Back</button>
            <button className="btn pri" disabled={busy || !authorized} onClick={create}>Create business</button>
          </div>
          {!authorized && <p className="note">Tick the authorization box to create the business. You become its Super Admin.</p>}
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
