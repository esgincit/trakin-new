"use client";

import { useRef, useState } from "react";
import { Chip, Field, formValues, Modal, useAction, useToast } from "./ui";
import { api, ApiError, setTenant } from "@/lib/api";

type Country = "US" | "IN";
/** A new business can play any role (vendor on one engagement, client on another),
 *  so creation doesn't ask — every company starts with all roles, narrowed later
 *  on the company profile if ever needed. */
const ALL_KINDS = ["client", "prime_vendor", "vendor", "end_client"];

/** Country-first business creation.
 *  US: W-9 upload (parsed + validated) → domain/e-mail/DBA → OTP → authorize → created.
 *  IN: manual details + mandatory MOA → domain/e-mail/DBA → OTP → authorize → created.
 *  Nothing is created until every gate passes; the creator becomes its owner.
 *  account: registering your own company — it gets its own account and waits for platform activation.
 *  Otherwise a client/vendor record is added inside the current company. */
export function CompanyWizard({ onClose, onDone, account = false }: { onClose: () => void; onDone: (c: any) => void; account?: boolean }) {
  const { run, busy } = useAction();
  const toast = useToast();
  const [country, setCountry] = useState<Country | null>(null);
  const [session, setSession] = useState<any>(null);
  const [step, setStep] = useState(1);
  const [parsed, setParsed] = useState<any>(null);
  const [manual, setManual] = useState(false);
  const [otpSent, setOtpSent] = useState(false);
  const [authorized, setAuthorized] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const w9file = useRef<HTMLInputElement>(null);
  const moafile = useRef<HTMLInputElement>(null);

  const start = async (c: Country) => {
    setError(null);
    const s = await run(() => api<any>(account ? "/onboarding/accounts" : "/onboarding/sessions", { body: { country: c } }));
    if (s?.tenant_id) setTenant(s.tenant_id);   // the rest of the wizard runs inside the new company
    if (s) { setCountry(c); setSession(s); setStep(1); }
  };

  const fail = (e: unknown) => {
    const message = (e as ApiError).message;
    setError(message);   // persistent inline error
    toast(message);      // transient toast with the exact backend message
  };

  const uploadW9 = async (file?: File) => {
    if (!file || !session) return;
    setError(null);
    setManual(false);
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
      const s = await api(`/onboarding/sessions/${session.id}`, { method: "PATCH", body: { ...formValues(e.currentTarget), kinds: ALL_KINDS, kind: ALL_KINDS[0], step: 2 } });
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
      if (!c?.id) throw new Error("The business was saved but returned no ID — find it in My businesses.");
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
          <p className="muted">Upload the signed W-9 (PDF or photo) — legal name, business type, EIN and address are read automatically and the EIN is checked for duplicates — or enter the details manually. With a manual entry you can upload the W-9 after the company is created; the platform verifies it before activation.</p>
          <input ref={w9file} type="file" accept="application/pdf,image/jpeg,image/png,image/webp" hidden onChange={(e) => uploadW9(e.target.files?.[0])} />
          <div className="row mt">
            <button className="btn pri" disabled={busy} onClick={() => w9file.current?.click()}>Upload W-9</button>
            <button className="btn" disabled={busy} onClick={() => { setError(null); setManual(true); setParsed({}); }}>Fill details manually</button>
          </div>
          {error && <p className="mt"><button className="btn" disabled={busy} onClick={() => { setError(null); setManual(true); setParsed({}); }}>Enter details manually instead</button></p>}
        </>
      )}

      {step === 1 && country === "US" && parsed && (
        <form className="form" onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          try {
            const v: any = { ...parsed, ...formValues(e.currentTarget), kinds: ALL_KINDS, kind: ALL_KINDS[0], step: 1 };
            if (manual) v.manual = true;
            delete v.engine; delete v.needs_review; delete v.needs_manual; delete v.note;
            if (manual) v.manual = true;
            const s = await api(`/onboarding/sessions/${session.id}`, { method: "PATCH", body: v });
            setSession(s); setStep(2);
          } catch (e) { fail(e); }
        }}>
          <p className="muted">{manual ? "Type the W-9 details exactly as they appear on the form." : `Read from the W-9${parsed.engine === "ocr" ? " (scan)" : parsed.engine === "form-fields" ? " (form fields)" : ""} — correct anything misread.`}</p>
          <div className="fields">
            <Field label="Legal name" name="legal_name" required defaultValue={parsed.legal_name ?? ""} full />
            <Field label="Business type" name="business_type" as="select" defaultValue={parsed.tax_classification ?? ""}
                   options={[["", "Choose…"], ["Individual / sole proprietorship", "Individual / sole proprietorship"], ["LLC", "LLC"], ["Partnership", "Partnership"], ["Corporation", "Corporation"], ["S Corporation", "S Corporation"], ["Trust / estate", "Trust / estate"]]} />
            <Field label="ID type" name="tin_type" as="select" defaultValue={parsed.tin_type ?? "ein"} options={[["ein", "EIN"], ["ssn", "SSN (sole proprietor)"]]} />
            <Field label="EIN / SSN" name="ein" required defaultValue={parsed.tin ?? ""} />
            <Field label="Address" name="address" defaultValue={parsed.address ?? ""} full />
            <Field label="City" name="city" defaultValue={parsed.city ?? ""} />
            <Field label="State" name="state" defaultValue={parsed.state ?? ""} maxLength={2} />
            <Field label="ZIP" name="zip" defaultValue={parsed.zip ?? ""} />
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
          const v: any = { ...formValues(e.currentTarget), step: 1 };
          try {
            const s = await api(`/onboarding/sessions/${session.id}`, { method: "PATCH", body: { ...v, kinds: ALL_KINDS, kind: ALL_KINDS[0] } });
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
          {!authorized && <p className="note">{account
            ? "Tick the authorization box to create your company. You become its owner; the myTrakIn team activates it after a quick review."
            : "Tick the authorization box to create the business. You become its owner."}</p>}
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
