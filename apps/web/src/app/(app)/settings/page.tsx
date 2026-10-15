"use client";

import { Chip, ErrorBox, Field, formValues, Loading, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, label } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

const SETUP = ["Company details", "Invite your team", "Add clients & vendors", "Import existing data", "Add MSAs & SOWs", "Projects & placements", "Policies & reminders", "Go live"];

const SWITCHES: [string, string, string][] = [
  ["requireNDA", "Require NDA", "A client or vendor needs a signed NDA before its MSA, and before a project with it goes active."],
  ["requireMSA", "Require MSA", "Projects, invoices and vendor payments need an active MSA (or subcontract / 1099 agreement)."],
  ["requireContract", "Require resource contract", "Timesheets need the resource's work order (vendor / 1099) or offer letter (W-2)."],
  ["requireAcceptance", "Require acceptance", "That contract and the client SOW must be signed or accepted before timesheets."],
];
const ENTITIES: Record<string, string> = {
  project: "Project", msa: "MSA", subcontract: "Subcontract", ica: "1099 agreement", nda: "NDA", offer_letter: "Offer letter",
  sow: "Client SOW", contract: "Resource contract (work order)", invoice_ar: "Client invoice", invoice_ap: "Vendor payable", envelope: "E-sign envelope",
};

export default function Settings() {
  const { data: t, error, loading, reload } = useApi("/workspace");
  const workflow = useApi<Record<string, boolean>>("/workspace/workflow");
  const numbering = useApi<Record<string, { template: string; next: string }>>("/workspace/numbering");
  const { run, busy } = useAction();
  const { workspace } = useSession();
  if (workspace && !allows(workspace, "tenant_admin")) {
    return <PageHead title="Workspace settings" sub="Only the workspace admin can change these settings." />;
  }
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  const s = t.settings ?? {};
  return (
    <>
      <PageHead title="Workspace settings" sub={<>{t.name} · {label(t.plan)} plan · <Chip status={t.status} />{t.trial_ends_on && ` · trial until ${date(t.trial_ends_on)}`}</>} />
      <div className="card">
        <h3>Setup checklist</h3>
        <div className="steps">
          {SETUP.map((step, i) => (
            <div key={step} className={`step ${i + 1 < t.onboarding_step ? "done" : i + 1 === t.onboarding_step ? "cur" : ""}`}>
              <span className="dot">{i + 1 < t.onboarding_step ? "✓" : i + 1}</span><div><b style={{ fontSize: 12.5 }}>{step}</b></div>
            </div>
          ))}
        </div>
        {t.onboarding_step < 8 && <button className="btn sm mt" disabled={busy} onClick={async () => { if (await run(() => api("/workspace/onboarding-step", { method: "POST", query: { step: t.onboarding_step + 1 } }), "Step done")) reload(); }}>Mark “{SETUP[t.onboarding_step - 1]}” done</button>}
      </div>
      <div className="grid c2 mt">
        <form className="card form" onSubmit={async (e) => {
          e.preventDefault();
          if (await run(() => api("/workspace", { method: "PATCH", body: formValues(e.currentTarget) }), "Saved")) reload();
        }}>
          <h3>Company</h3>
          <Field label="Display name" name="name" defaultValue={t.name} />
          <Field label="Legal name" name="legal_name" defaultValue={t.legal_name ?? ""} />
          <div className="fields">
            <Field label="EIN" name="ein" defaultValue={t.ein ?? ""} />
            <Field label="State" name="state" defaultValue={t.state ?? ""} maxLength={2} />
          </div>
          <button className="btn pri mt" disabled={busy}>Save</button>
        </form>
        <form className="card form" onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const settings = {
            sign_in: { email_code: !!f.get("email_code"), sms_code: !!f.get("sms_code"), sso: !!f.get("sso"), google: !!f.get("google"), microsoft: !!f.get("microsoft"), password: !!f.get("password") },
            sso_domain: f.get("sso_domain") || null,
            mfa_for_all: !!f.get("mfa_for_all"),
            session_hours: Number(f.get("session_hours") || 12),
            invoice_footer: f.get("invoice_footer") || null,
          };
          if (await run(() => api("/workspace", { method: "PATCH", body: { settings } }), "Security settings saved")) reload();
        }}>
          <h3>Sign-in & security</h3>
          {[["email_code", "E-mail one-time code"], ["sms_code", "Text message code"], ["sso", "Company SSO (SAML)"], ["google", "Google"], ["microsoft", "Microsoft"], ["password", "Password"]].map(([k, l]) => (
            <label key={k} className="row" style={{ color: "var(--ink)" }}><input type="checkbox" className="toggle" name={k} defaultChecked={s.sign_in?.[k] ?? k !== "password"} /> {l}</label>
          ))}
          <Field label="SSO domain" name="sso_domain" defaultValue={s.sso_domain ?? ""} placeholder="yourcompany.com" />
          <label className="row" style={{ color: "var(--ink)" }}><input type="checkbox" className="toggle" name="mfa_for_all" defaultChecked={!!s.mfa_for_all} /> Require two-step verification for every staff user (always on for admin and finance)</label>
          <Field label="Sign out after (hours idle)" name="session_hours" type="number" min={1} max={720} defaultValue={s.session_hours ?? 12} />
          <Field label="Invoice footer" name="invoice_footer" as="textarea" defaultValue={s.invoice_footer ?? ""} placeholder="Remit to: … ACH routing …" />
          <p className="note">Which methods actually work also depends on the providers enabled in your Supabase project (Authentication → Providers).</p>
          <button className="btn pri mt" disabled={busy}>Save</button>
        </form>
      </div>
      <div className="grid c2 mt">
        <form className="card form" onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const values = Object.fromEntries(SWITCHES.map(([k]) => [k, !!f.get(k)]));
          if (await run(() => api("/workspace", { method: "PATCH", body: { settings: { workflow: values } } }), "Workflow saved")) workflow.reload();
        }}>
          <h3>Workflow</h3>
          <p className="muted">Register → Verify → NDA → MSA → Project → SOW → Acceptance → Resource contract → Acceptance → Timesheet → Invoice → Payment → Confirmation.</p>
          {workflow.data && SWITCHES.map(([k, l, help]) => (
            <label key={k} className="row" style={{ color: "var(--ink)", alignItems: "flex-start" }}>
              <input type="checkbox" className="toggle" name={k} defaultChecked={workflow.data![k]} />
              <span><b>{l}</b><div className="muted" style={{ fontSize: 12.5 }}>{help}</div></span>
            </label>
          ))}
          <button className="btn pri mt" disabled={busy}>Save</button>
        </form>
        <form className="card form" onSubmit={async (e) => {
          e.preventDefault();
          const v = formValues(e.currentTarget) as Record<string, string>;
          const changed = Object.fromEntries(Object.entries(v).filter(([k, val]) => val && val !== numbering.data?.[k]?.template));
          if (!Object.keys(changed).length) return;
          if (await run(() => api("/workspace", { method: "PATCH", body: { settings: { numbering: changed } } }), "Numbering saved")) numbering.reload();
        }}>
          <h3>Numbering</h3>
          <p className="muted">Placeholders: {"{YEAR} {YY} {MM} {YYYYMM} {SEQ} {SEQ:4} {CLIENT} {PROJECT}"}. Every template needs {"{SEQ}"}.</p>
          {numbering.data && Object.entries(numbering.data).map(([k, n]) => (
            <Field key={k} label={`${ENTITIES[k] ?? k} — next: ${n.next}`} name={k} defaultValue={n.template} />
          ))}
          <button className="btn pri mt" disabled={busy}>Save</button>
        </form>
      </div>
    </>
  );
}
