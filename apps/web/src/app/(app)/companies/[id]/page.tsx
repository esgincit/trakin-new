"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Attachments } from "@/components/Attachments";
import { CheckList } from "@/components/CompanyWizard";
import { CompanyPicker } from "@/components/CompanyPicker";
import { CompanyForm } from "@/components/forms";
import { Avatar, Bar, Chip, ErrorBox, Field, formValues, Loading, Modal, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { AGREEMENT_TERMS, date, label, money, roleList } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

const STAGES = ["Registered", "Verified", "Documents", "MSA signed", "SOW signed", "Project set up", "Timesheets", "Invoicing"];

export default function CompanyDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { workspace } = useSession();
  const { data: c, error, loading, reload } = useApi(`/companies/${id}`);
  const [editing, setEditing] = useState(false);
  const [msaOpen, setMsaOpen] = useState(false);
  const [memberRole, setMemberRole] = useState("member");
  const logo = useRef<HTMLInputElement>(null);
  const w9file = useRef<HTMLInputElement>(null);
  const { run, busy } = useAction();
  const { refresh } = useSession();
  const canEdit = allows(workspace, "account_manager", "finance", "legal");
  const canDecideW9 = allows(workspace, "finance", "legal");
  const myRole = c?.my_company_role;
  const isTenantAdmin = allows(workspace, "tenant_admin");
  const ownerLike = ["super_admin", "owner", "admin"].includes(myRole);
  const canManage = canEdit || ownerLike;
  const canGrantSuper = myRole === "super_admin" || isTenantAdmin;
  const canGrantOwner = canGrantSuper || myRole === "owner";
  const taxFull = allows(workspace, "finance", "legal") || ownerLike;

  if (loading) return <Loading rows={8} />;
  if (error) return <ErrorBox error={error} retry={reload} />;

  return (
    <>
      <PageHead title={c.name}
        sub={<>{c.logo_url && <img src={c.logo_url} alt="" style={{ height: 26, borderRadius: 6, verticalAlign: "middle", marginRight: 8 }} />}{c.business_code} · {c.country} · {roleList(c)} · <Chip status={c.status} />{c.inactive_since && ` since ${date(c.inactive_since)} — ${c.inactive_reason ?? ""}`}</>}
        actions={<>
          <button className="btn" onClick={() => router.back()}>Back</button>
          {canEdit && <button className="btn" onClick={() => setEditing(true)}>Edit</button>}
          {canManage && <button className="btn" onClick={() => setMsaOpen(true)}>New MSA</button>}
        {canEdit && (c.status === "inactive" ? (
            <button className="btn" disabled={busy} onClick={async () => { if (await run(() => api(`/companies/${id}/status`, { body: { status: "active" } }), "Reactivated")) reload(); }}>Reactivate</button>
          ) : (
            <button className="btn" disabled={busy} onClick={async () => {
              const reason = prompt("Why is this company becoming inactive? (history is kept)");
              if (reason && await run(() => api(`/companies/${id}/status`, { body: { status: "inactive", reason } }), "Marked inactive")) reload();
            }}>Mark inactive</button>
          ))}
        </>} />

      <div className="card">
        <h3>Onboarding</h3>
        <div className="steps">
          {STAGES.map((s, i) => (
            <div key={s} className={`step ${i + 1 < c.onboarding_stage ? "done" : i + 1 === c.onboarding_stage ? "cur" : ""}`}>
              <span className="dot">{i + 1 < c.onboarding_stage ? "✓" : i + 1}</span><div><b style={{ fontSize: 12.5 }}>{s}</b></div>
            </div>
          ))}
        </div>
        {canEdit && c.onboarding_stage < 8 && (
          <button className="btn sm mt" onClick={async () => { if (await run(() => api(`/companies/${id}`, { method: "PATCH", body: { onboarding_stage: c.onboarding_stage + 1 } }), "Stage completed")) reload(); }}>
            Mark “{STAGES[c.onboarding_stage - 1]}” done
          </button>
        )}
      </div>

      <div className="grid c2 mt">
        <div className="card">
          <h3>Details</h3>
          <dl className="dl">
            <dt>Business ID</dt><dd><code>{c.business_code}</code></dd>
            <dt>Country</dt><dd>{c.country === "IN" ? "India" : "United States"}</dd>
            {c.cin && <><dt>CIN</dt><dd>{taxFull ? c.cin : `${c.cin.slice(0, 5)}••••••••••••••`}</dd></>}
            <dt>Domain</dt><dd>{c.domain ?? "–"}</dd>
            {c.business_type && <><dt>Business type</dt><dd>{c.business_type}</dd></>}
            {c.dba && <><dt>DBA</dt><dd>{c.dba}</dd></>}
            <dt>Contact</dt><dd>{c.contact_name ?? "–"} {c.contact_email && <a href={`mailto:${c.contact_email}`}>{c.contact_email}</a>}</dd>
            <dt>Phone</dt><dd>{c.contact_phone ?? "–"}</dd>
            <dt>State</dt><dd>{c.state ?? "–"}</dd>
            <dt>EIN</dt><dd>{c.ein ?? <span className="masked">••••</span>}</dd>
            <dt>Payment terms</dt><dd>{c.default_terms}</dd>
            <dt>Bank verified</dt><dd>{c.bank_verified ? "Yes" : "No"}</dd>
            {c.balances && <><dt>Open AR</dt><dd>{money(c.balances.open_ar)}</dd><dt>Open AP</dt><dd>{money(c.balances.open_ap)}</dd></>}
          </dl>
          {canManage && <>
            <input ref={logo} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              const form = new FormData();
              form.set("file", f);
              if (await run(() => api(`/companies/${id}/logo`, { form }), "Logo updated")) { reload(); refresh(); }
            }} />
            <button className="btn sm mt" onClick={() => logo.current?.click()}>Upload logo</button>
          </>}
          {c.notes && <p className="note">{c.notes}</p>}
        </div>
        <div className="card">
          <h3>Agreements</h3>
          {c.agreements.map((a: any) => (
            <div key={a.id} className="alert click" onClick={() => router.push(`/contracts/agreements/${a.id}`)}>
              <Chip status={a.status} /><div><b>{a.code}</b> · {label(a.kind)}<div className="muted" style={{ fontSize: 12.5 }}>{date(a.effective_on)} – {date(a.expires_on)} · {a.payment_terms ?? ""} {a.source !== "myTrakIn" && `· ${a.source}`}</div></div>
            </div>
          ))}
          {!c.agreements.length && <p className="muted">No MSA yet. <Link href="/contracts?new=agreement">Add one</Link> or send one for signature.</p>}
          <h3 className="mt">SOWs / work orders</h3>
          {c.sows.map((s: any) => (
            <div key={s.id} className="alert click" onClick={() => router.push(`/contracts/sows/${s.id}`)}>
              <div style={{ flex: 1 }}><b>{s.code}</b> {s.title}<div className="muted" style={{ fontSize: 12.5 }}>{label(s.side)} · ends {date(s.end_date)}</div></div>
              <div style={{ width: 90 }}><Bar pct={s.burn_pct} /></div>
            </div>
          ))}
        </div>
      </div>

      {c.status === "onboarding" && (
        <div className="card mt">
          <h3>Verification</h3>
          {c.verification && Object.keys(c.verification).length > 0
            ? <CheckList checks={c.verification} blockers={[]} />
            : <p className="muted">Not checked yet. Activation needs every check to pass: details complete, e-mail on the company domain, verified W-9 with matching TIN, and an assigned owner.</p>}
          <div className="row mt">
            {canManage && <button className="btn sm" disabled={busy} onClick={async () => { if (await run(() => api(`/companies/${id}/verify`, { method: "POST", body: {} }), "Verification re-run")) reload(); }}>Re-check</button>}
            {canEdit && <button className="btn sm pri" disabled={busy} onClick={async () => { if (await run(() => api(`/companies/${id}/activate`, { method: "POST", body: {} }), `Activated as ${c.business_code}`)) reload(); }}>Activate company</button>}
          </div>
        </div>
      )}

      <div className="card mt">
        <h3>Tax & W-9 <Chip status={c.w9_status} /></h3>
        {c.w9_status === "rejected" && (
          <p className="err" role="alert" style={{ fontSize: 14, marginTop: 0 }}>
            This W-9 was rejected{c.w9_note ? <>: “{c.w9_note}”</> : " — ask finance or legal what was wrong"}.
            Upload a corrected copy below{taxFull ? ", fix the tax details, and have it verified again" : ", then ask finance or legal to review it again"}.
          </p>
        )}
        {taxFull ? (
          <dl className="dl">
            <dt>Legal name</dt><dd>{c.w9_data?.legal_name ?? "–"}</dd>
            <dt>Classification</dt><dd>{c.tax_classification ?? c.w9_data?.tax_classification ?? "–"}</dd>
            <dt>TIN</dt><dd>{c.tin ?? c.w9_data?.tin ?? "–"}</dd>
            <dt>Tax address</dt><dd>{c.tax_address ?? ([c.w9_data?.address, c.w9_data?.city, c.w9_data?.state, c.w9_data?.zip].filter(Boolean).join(", ") || "–")}</dd>
            {c.w9_note && <><dt>Review note</dt><dd>{c.w9_note}</dd></>}
          </dl>
        ) : (
          <p className="muted">W-9 is {label(c.w9_status)}. Tax details are visible to finance, legal and company owners/admins.</p>
        )}
        {canManage && <>
          <input ref={w9file} type="file" accept="application/pdf,image/jpeg,image/png,image/webp" hidden onChange={async (e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            const form = new FormData();
            form.set("file", f);
            if (await run(() => api(`/companies/${id}/w9`, { form }), "W-9 uploaded — review the tax details")) reload();
          }} />
          <div className="row mt">
            <button className="btn sm" onClick={() => w9file.current?.click()}>Upload W-9</button>
            {canDecideW9 && c.w9_status !== "verified" && (
              <button className="btn sm" disabled={busy} onClick={async () => { if (await run(() => api(`/companies/${id}/w9/decision`, { body: { decision: "verified" } }), "W-9 verified")) reload(); }}>Mark verified</button>
            )}
            {canDecideW9 && ["submitted", "under_review"].includes(c.w9_status) && (
              <button className="btn sm" disabled={busy} onClick={async () => {
                const note = prompt("What's wrong with this W-9?");
                if (note && await run(() => api(`/companies/${id}/w9/decision`, { body: { decision: "rejected", note } }), "W-9 sent back")) reload();
              }}>Reject</button>
            )}
          </div>
          {taxFull && <TaxForm id={id as string} c={c} reload={reload} />}
        </>}
      </div>

      <div className="card mt">
        <h3>Members{myRole ? ` — you are ${label(myRole)}` : ""}</h3>
        {(c.members ?? []).map((m: any) => (
          <div key={m.id} className="alert">
            <Avatar name={m.name} /><div style={{ flex: 1 }}><b>{m.name}</b><div className="muted" style={{ fontSize: 12.5 }}>{m.email} · {label(m.company_role)}{m.title ? ` · ${m.title}` : ""} · {label(m.status)}</div></div>
            {canManage && m.status === "active" && <>
              {m.company_role === "member" && <button className="btn sm" disabled={busy} onClick={async () => { if (await run(() => api(`/companies/${id}/members/${m.id}`, { method: "PATCH", body: { company_role: "admin" } }), "Made admin")) reload(); }}>Make admin</button>}
              {m.company_role === "admin" && <button className="btn sm" disabled={busy} onClick={async () => { if (await run(() => api(`/companies/${id}/members/${m.id}`, { method: "PATCH", body: { company_role: "member" } }), "Made member")) reload(); }}>Make member</button>}
              {(m.company_role === "member" || m.company_role === "admin") && canGrantOwner && <button className="btn sm" disabled={busy} onClick={async () => { if (await run(() => api(`/companies/${id}/members/${m.id}`, { method: "PATCH", body: { company_role: "owner" } }), "Now a co-owner")) reload(); }}>Make co-owner</button>}
              {m.company_role === "super_admin" && canGrantSuper && <button className="btn sm" disabled={busy} onClick={async () => { if (await run(() => api(`/companies/${id}/members/${m.id}`, { method: "PATCH", body: { company_role: "owner" } }), "Now a co-owner")) reload(); }}>Make co-owner</button>}
              <button className="btn sm" disabled={busy} onClick={async () => { if (await run(() => api(`/companies/${id}/members/${m.id}`, { method: "DELETE" }), "Removed")) reload(); }}>Remove</button>
            </>}
          </div>
        ))}
        {!(c.members ?? []).length && <p className="muted">No members yet.</p>}
        {canManage && (
          <form className="form mt" onSubmit={async (e) => {
            e.preventDefault();
            const v: any = formValues(e.currentTarget);
            if (await run(() => api(`/companies/${id}/members`, { body: { ...v, company_role: memberRole } }), "Member invited")) { reload(); (e.target as HTMLFormElement).reset(); }
          }}>
            <div className="row">
              <input className="ctl" name="email" type="email" required placeholder="person@company.com" style={{ flex: 2 }} aria-label="E-mail" />
              <select className="ctl" value={memberRole} onChange={(e) => setMemberRole(e.target.value)} aria-label="Role" style={{ flex: 1 }}>
                <option value="member">Member</option><option value="admin">Admin</option><option value="owner">Owner</option>
                {canGrantSuper && <option value="super_admin">Owner</option>}
              </select>
              <button className="btn sm pri" disabled={busy}>Invite</button>
            </div>
          </form>
        )}
      </div>
      {c.documents.length > 0 && (
        <div className="card mt">
          <h3>Tracked documents</h3>
          {c.documents.map((d: any) => <div key={d.id} className="alert"><Chip status={d.status} /><b>{d.label}</b> {d.expires_on && `· expires ${date(d.expires_on)}`} {d.blocks && `· blocks ${d.blocks}`}</div>)}
        </div>
      )}
      <Attachments ownerType="company" ownerId={id} canEdit={canEdit} />
      {editing && <Modal title={`Edit ${c.name}`} onClose={() => setEditing(false)}><CompanyForm initial={c} onSaved={() => { setEditing(false); reload(); }} /></Modal>}
      {msaOpen && <CompanyMsaModal company={c} onClose={() => setMsaOpen(false)} onDone={() => { setMsaOpen(false); reload(); }} />}
    </>
  );
}

function CompanyMsaModal({ company, onClose, onDone }: { company: any; onClose: () => void; onDone: () => void }) {
  const [existing, setExisting] = useState(true);
  const [counterparty, setCounterparty] = useState("");
  const { run, busy } = useAction();
  return (
    <Modal title={`New MSA — ${company.name}`} onClose={onClose}>
      <div className="seg" style={{ marginBottom: 8 }}>
        <button type="button" className={existing ? "on" : ""} onClick={() => setExisting(true)}>Already signed (record it)</button>
        <button type="button" className={!existing ? "on" : ""} onClick={() => setExisting(false)}>Request new MSA</button>
      </div>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        const v: any = formValues(e.currentTarget);
        const body = { ...v, existing, counterparty_company_id: counterparty || undefined };
        const r = await run(() => api(`/companies/${company.id}/msas`, { body }), "MSA sent — pending their acceptance");
        if (r) onDone();
      }}>
        <div className="fields">
          <CompanyPicker label="Other company" name="counterparty_company_id" required value={counterparty} excludeId={company.id} onChange={(e: any) => setCounterparty(e.target.value)} />
          <Field label="Type" name="kind" as="select" defaultValue="msa" options={[["msa", "MSA"], ["subcontract", "Subcontract"]]} />
          <Field label="We are the" name="tenant_side" as="select" defaultValue="supplier" options={[["supplier", "Supplier"], ["buyer", "Buyer"]]} />
          <Field label="Effective" name="effective_on" type="date" />
          <Field label="Expires" name="expires_on" type="date" />
          <Field label="Payment terms" name="payment_terms" as="select" options={AGREEMENT_TERMS.payment_terms} />
          {existing
            ? <Field label="Signed by" name="signed_by" full />
            : <Field label="Message to the other company" name="note" as="textarea" full />}
        </div>
        <button className="btn pri mt" disabled={busy || !counterparty}>Send</button>
      </form>
    </Modal>
  );
}

function TaxForm({ id, c, reload }: { id: string; c: any; reload: () => void }) {
  const { run, busy } = useAction();
  return (
    <form className="form mt" onSubmit={async (e) => {
      e.preventDefault();
      if (await run(() => api(`/companies/${id}/tax`, { method: "PATCH", body: formValues(e.currentTarget) }), "Tax details saved")) reload();
    }}>
      <div className="fields">
        <Field label="DBA" name="dba" defaultValue={c.dba ?? c.w9_data?.dba ?? ""} />
        <Field label="Tax classification" name="tax_classification" defaultValue={c.tax_classification ?? c.w9_data?.tax_classification ?? ""} />
        <Field label="TIN type" name="tin_type" as="select" defaultValue="ein" options={[["ein", "EIN"], ["ssn", "SSN"]]} />
        <Field label="TIN" name="tin" defaultValue={c.tin ?? ""} placeholder="12-3456789" />
        <Field label="EIN (company record)" name="ein" defaultValue={c.ein ?? ""} />
        <Field label="Tax address" name="tax_address" defaultValue={c.tax_address ?? ""} full />
      </div>
      <button className="btn sm mt" disabled={busy}>Save tax details</button>
    </form>
  );
}
