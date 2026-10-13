"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { DataButtons } from "@/components/DataButtons";
import { DataTable, type Column } from "@/components/DataTable";
import { Chip, Drawer, ErrorBox, Field, formValues, Modal, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, dateTime, daysLeft, label } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

type Tab = "documents" | "work_auth" | "policies" | "registrations" | "reminders";

export default function CompliancePage() {
  return <Suspense><Compliance /></Suspense>;
}

function Compliance() {
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) ?? (params.get("doc") ? "documents" : "documents"));
  const tabs: [Tab, string][] = [["documents", "Expiring documents"], ["work_auth", "Work authorization & I-9"], ["policies", "Policies"], ["registrations", "Registrations"], ["reminders", "Reminders & e-mails"]];
  return (
    <>
      <PageHead title="Compliance" sub="Work authorization, I-9 reverification, expiring documents, policies and new registrations. Reminders go out automatically." />
      <div className="tabs">{tabs.map(([k, t]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{t}</button>)}</div>
      {tab === "documents" && <Documents />}
      {tab === "work_auth" && <WorkAuth />}
      {tab === "policies" && <Policies />}
      {tab === "registrations" && <Registrations />}
      {tab === "reminders" && <Reminders />}
    </>
  );
}

function Documents() {
  const { workspace } = useSession();
  const { data, error, reload } = useApi<any[]>("/compliance/documents");
  const consultants = useApi<any[]>("/consultants");
  const [adding, setAdding] = useState(false);
  const [renewing, setRenewing] = useState<any>(null);
  const { run, busy } = useAction();
  const canEdit = allows(workspace, "hr", "legal");
  const cols: Column<any>[] = [
    { key: "owner", label: "Person / company" }, { key: "label", label: "Document" },
    { key: "doc_type", label: "Type", type: "label", filter: true },
    { key: "expires_on", label: "Expires", type: "date" },
    { key: "days_left", label: "When", render: (r) => daysLeft(r.days_left), value: (r) => r.days_left },
    { key: "urgency", label: "Urgency", type: "status", filter: true },
    { key: "blocks", label: "Holds", hideSm: true },
    { key: "last_notified_on", label: "Last reminder", type: "date", hideSm: true },
  ];
  return (
    <>
      <ErrorBox error={error} retry={reload} />
      <DataTable id="tracked-docs" rows={data} columns={cols} onRowClick={canEdit ? setRenewing : undefined}
        toolbar={<>{canEdit && <button className="btn sm pri" onClick={() => setAdding(true)}>Track a document</button>}<DataButtons entity="tracked_documents" label="documents" /></>} />
      <p className="note">E-mails go to the person, HR and any extra recipients 120, 90, 60, 30, 14 and 7 days before expiry, on the day, and weekly after until renewed. I-9 reminders include the Supplement B (reverification) step.</p>
      {adding && (
        <Modal title="Track an expiring document" onClose={() => setAdding(false)}>
          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            const v: any = formValues(e.currentTarget);
            v.recipients = v.recipients ? v.recipients.split(/[;,]/).map((s: string) => s.trim()).filter(Boolean) : [];
            if (await run(() => api("/compliance/documents", { body: v }), "Tracking — reminders are scheduled")) { setAdding(false); reload(); }
          }}>
            <div className="fields">
              <Field label="Consultant" name="consultant_id" as="select" options={[["", "Choose…"], ...(consultants.data ?? []).map((c) => [c.id, c.full_name] as [string, string])]} full />
              <Field label="Type" name="doc_type" as="select" options={["i9_reverification", "passport", "ead", "i94", "visa_notice", "coi", "w9", "background_check", "certification", "drivers_license", "other"]} />
              <Field label="Label" name="label" required placeholder="EAD (STEM OPT)" />
              <Field label="Expires on" name="expires_on" type="date" />
              <Field label="Holds while expired" name="blocks" placeholder="timesheets, payouts" />
              <Field label="Extra e-mail recipients (; separated)" name="recipients" full />
            </div>
            <button className="btn pri mt" disabled={busy}>Start tracking</button>
          </form>
        </Modal>
      )}
      <Drawer open={!!renewing} onClose={() => setRenewing(null)} title={renewing ? `${renewing.owner}: ${renewing.label}` : ""}>
        {renewing && (
          <>
            <dl className="dl"><dt>Type</dt><dd>{label(renewing.doc_type)}</dd><dt>Expires</dt><dd>{date(renewing.expires_on)} ({daysLeft(renewing.days_left)})</dd><dt>Status</dt><dd><Chip status={renewing.status} /></dd><dt>Recipients</dt><dd>{renewing.recipients?.join(", ") || "Person + HR"}</dd></dl>
            <form className="form" onSubmit={async (e) => {
              e.preventDefault();
              if (await run(() => api(`/compliance/documents/${renewing.id}/renew`, { body: formValues(e.currentTarget) }), "Renewal recorded")) { setRenewing(null); reload(); }
            }}>
              <Field label="New expiry date" name="expires_on" type="date" required />
              <button className="btn pri mt" disabled={busy}>Record renewal</button>
            </form>
            <p className="note mt"><a onClick={async () => { if (confirm("Stop tracking this document?") && await run(() => api(`/compliance/documents/${renewing.id}`, { method: "DELETE" }), "Stopped")) { setRenewing(null); reload(); } }}>Stop tracking</a></p>
          </>
        )}
      </Drawer>
    </>
  );
}

function WorkAuth() {
  const { data, error, reload } = useApi<any[]>("/compliance/work-authorization");
  return (
    <>
      <ErrorBox error={error} retry={reload} />
      <DataTable id="work-auth" rows={data} columns={[
        { key: "full_name", label: "Consultant" }, { key: "engagement", label: "Type", type: "label", filter: true },
        { key: "work_auth_type", label: "Authorization" }, { key: "work_auth_expires", label: "Valid until", type: "date" },
        { key: "days_left", label: "When", render: (r) => daysLeft(r.days_left), value: (r) => r.days_left },
        { key: "i9_status", label: "Form I-9", hideSm: true }, { key: "everify_status", label: "E-Verify", hideSm: true },
        { key: "finding", label: "Finding", filter: true, render: (r) => <Chip status={r.finding === "OK" ? "ok" : /expired|not recorded/i.test(r.finding) ? "overdue" : /due/i.test(r.finding) ? "pending" : ""}>{r.finding}</Chip> },
      ]} />
      <p className="note">This is a tracking aid, not legal advice. For W-2 employees, complete Form I-9 Section 1 by the first day and Section 2 within three business days; reverify before work authorization expires. C2C vendors are responsible for their own employees' I-9.</p>
    </>
  );
}

function Policies() {
  const { workspace } = useSession();
  const { data, error, reload } = useApi<any[]>("/policies");
  const [adding, setAdding] = useState(false);
  const [viewing, setViewing] = useState<any>(null);
  const acceptances = useApi<any[]>(viewing ? `/policies/${viewing.id}/acceptances` : null);
  const { run, busy } = useAction();
  return (
    <>
      <ErrorBox error={error} retry={reload} />
      <DataTable id="policies" rows={data} onRowClick={setViewing} columns={[
        { key: "name", label: "Policy" }, { key: "version", label: "Version" }, { key: "effective_on", label: "Effective", type: "date" },
        { key: "applies_to", label: "Applies to", value: (r) => r.applies_to.map(label).join(", ") },
        { key: "progress", label: "Accepted", value: (r) => `${r.accepted}/${r.expected}` },
        { key: "active", label: "Status", render: (r) => <Chip status={r.active ? "active" : "inactive"} />, value: (r) => (r.active ? "Active" : "Retired") },
      ]} toolbar={allows(workspace, "hr", "legal") && <button className="btn sm pri" onClick={() => setAdding(true)}>Publish policy</button>} />
      {adding && (
        <Modal title="Publish a policy" onClose={() => setAdding(false)}>
          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            const groups = ["w2_fulltime", "w2_contract", "c2c", "1099"].filter((g) => form.get(`g_${g}`));
            ["w2_fulltime", "w2_contract", "c2c", "1099"].forEach((g) => form.delete(`g_${g}`));
            form.set("applies_to", groups.join(","));
            if (!(form.get("file") as File)?.name) form.delete("file");
            if (await run(() => api("/policies", { form }), "Published — consultants will be asked to accept it")) { setAdding(false); reload(); }
          }}>
            <div className="fields">
              <Field label="Name" name="name" required placeholder="Code of conduct" />
              <Field label="Version" name="version" required placeholder="v3" />
              <Field label="Effective" name="effective_on" type="date" required />
              <div><label htmlFor="pf">PDF</label><input id="pf" name="file" type="file" accept="application/pdf" className="ctl" /></div>
            </div>
            <label>Who must accept</label>
            <div className="row">{["w2_fulltime", "w2_contract", "c2c", "1099"].map((g) => <label key={g} className="row" style={{ color: "var(--ink)", margin: 0 }}><input type="checkbox" name={`g_${g}`} defaultChecked /> {label(g)}</label>)}</div>
            <p className="note">Publishing a new version retires the previous one; everyone is asked to accept again.</p>
            <button className="btn pri mt" disabled={busy}>Publish</button>
          </form>
        </Modal>
      )}
      <Drawer open={!!viewing} onClose={() => setViewing(null)} title={viewing ? `${viewing.name} ${viewing.version}` : ""}>
        <table><thead><tr><th>Consultant</th><th>Accepted</th><th>IP address</th></tr></thead>
          <tbody>{acceptances.data?.map((a) => <tr key={a.consultant_id}><td>{a.full_name}</td><td>{a.accepted_at ? dateTime(a.accepted_at) : <Chip status="pending" />}</td><td>{a.ip ?? "–"}</td></tr>)}</tbody></table>
      </Drawer>
    </>
  );
}

function Registrations() {
  const { workspace } = useSession();
  const { data, error, reload } = useApi<any[]>("/registrations");
  const [open, setOpen] = useState<string | null>(null);
  const detail = useApi(open ? `/registrations/${open}` : null);
  const { run, busy } = useAction();
  const link = typeof window !== "undefined" && workspace ? `${location.origin}/register/${workspace.tenant.id}` : "";
  const decide = async (decision: string) => {
    const note = decision === "approved" ? undefined : prompt(decision === "rejected" ? "Reason for rejecting (sent to the applicant):" : "What do you need from them?");
    if (decision !== "approved" && !note) return;
    if (await run(() => api(`/registrations/${open}/decision`, { body: { decision, note } }), `Registration ${decision.replace("_", " ")}`)) { setOpen(null); reload(); }
  };
  const openFile = async (id: string) => { const r = await run(() => api(`/files/${id}/link`)); if (r) window.open(r.url, "_blank", "noopener"); };
  return (
    <>
      <div className="card" style={{ marginBottom: 12 }}>
        <b>Your public registration page</b>
        <div className="row mt"><input className="ctl" readOnly value={link} style={{ flex: 1 }} aria-label="Registration link" /><button className="btn sm" onClick={() => navigator.clipboard.writeText(link)}>Copy</button></div>
        <p className="note">Share it with new vendors, clients and contractors. They upload W-9, incorporation and insurance documents; you approve here.</p>
      </div>
      <ErrorBox error={error} retry={reload} />
      <DataTable id="registrations" rows={data} onRowClick={(r) => setOpen(r.id)} columns={[
        { key: "name", label: "Name" }, { key: "kind", label: "Type", type: "label", filter: true }, { key: "contact", label: "Contact" },
        { key: "email", label: "E-mail", hideSm: true }, { key: "files", label: "Files", type: "number" },
        { key: "created_at", label: "Received", type: "date" }, { key: "status", label: "Status", type: "status", filter: true },
      ]} empty="No registrations yet." />
      <Drawer open={!!open} onClose={() => setOpen(null)} title={detail.data?.name ?? "Registration"}>
        {detail.data && (
          <>
            <dl className="dl">
              <dt>Type</dt><dd>{label(detail.data.kind)}</dd><dt>Contact</dt><dd>{detail.data.contact} · {detail.data.email} · {detail.data.phone ?? ""}</dd>
              <dt>State / EIN</dt><dd>{detail.data.state ?? "–"} · {detail.data.ein ?? "–"}</dd>
              <dt>Checks</dt><dd>{detail.data.checks.email_free_domain ? <Chip status="pending">Personal e-mail domain</Chip> : <Chip status="ok">Company e-mail</Chip>} {detail.data.checks.ein_given ? <Chip status="ok">EIN given</Chip> : <Chip status="pending">No EIN</Chip>}</dd>
              <dt>Submitted from</dt><dd>IP {detail.data.checks.submitted_ip ?? "–"}</dd>
            </dl>
            {detail.data.duplicates.length > 0 && <p className="err">Possible duplicate: {detail.data.duplicates.map((d: any) => d.name).join(", ")}</p>}
            <h3>Documents</h3>
            {detail.data.files.map((f: any) => <div key={f.id} className="alert"><a onClick={() => openFile(f.id)}>{f.name}</a></div>)}
            {!detail.data.files.length && <p className="muted">No documents uploaded.</p>}
            {detail.data.status !== "approved" && detail.data.status !== "rejected" && (
              <div className="row mt">
                <button className="btn pri" disabled={busy} onClick={() => decide("approved")}>Approve</button>
                <button className="btn" disabled={busy} onClick={() => decide("needs_info")}>Ask for more</button>
                <button className="btn" disabled={busy} onClick={() => decide("rejected")}>Reject</button>
              </div>
            )}
          </>
        )}
      </Drawer>
    </>
  );
}

function Reminders() {
  const { workspace } = useSession();
  const rules = useApi<any[]>("/reminder-rules");
  const log = useApi<any[]>("/notifications");
  const { run } = useAction();
  const admin = allows(workspace, "tenant_admin");
  return (
    <>
      <div className="tw">
        <table>
          <thead><tr><th>Area</th><th>Reminder</th><th>When (days)</th><th>On</th></tr></thead>
          <tbody>{rules.data?.map((r) => (
            <tr key={r.id}><td>{r.area}</td><td style={{ whiteSpace: "normal" }}>{r.description}</td>
              <td>{admin ? <input className="ctl" defaultValue={r.offsets.join(", ")} style={{ width: 160 }} aria-label={`Days for ${r.description}`}
                onBlur={async (e) => { const offsets = e.target.value.split(",").map((x) => parseInt(x.trim(), 10)).filter((x) => !Number.isNaN(x)); await run(() => api(`/reminder-rules/${r.id}`, { method: "PATCH", body: { offsets } }), "Saved"); }} /> : r.offsets.join(", ")}</td>
              <td><input type="checkbox" className="toggle" defaultChecked={r.enabled} disabled={!admin} aria-label="Enabled"
                onChange={async (e) => { await run(() => api(`/reminder-rules/${r.id}`, { method: "PATCH", body: { enabled: e.target.checked } }), e.target.checked ? "Turned on" : "Turned off"); }} /></td></tr>
          ))}</tbody>
        </table>
      </div>
      <p className="note">Negative numbers are days before the date; positive are days after. The daily job runs once a day, early morning US time (13:00 UTC).</p>
      <h3 className="mt">E-mails sent</h3>
      <DataTable id="notifications" rows={log.data} columns={[
        { key: "sent_at", label: "When", render: (r) => dateTime(r.sent_at), value: (r) => r.sent_at }, { key: "kind", label: "Kind", type: "label", filter: true },
        { key: "to_address", label: "To" }, { key: "subject", label: "Subject" }, { key: "status", label: "Status", type: "status", filter: true },
      ]} />
    </>
  );
}
