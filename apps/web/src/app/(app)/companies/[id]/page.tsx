"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Attachments } from "@/components/Attachments";
import { CompanyForm } from "@/components/forms";
import { Bar, Chip, ErrorBox, Loading, Modal, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, label, money } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

const STAGES = ["Registered", "Verified", "Documents", "MSA signed", "SOW signed", "Project set up", "Timesheets", "Invoicing"];

export default function CompanyDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { workspace } = useSession();
  const { data: c, error, loading, reload } = useApi(`/companies/${id}`);
  const [editing, setEditing] = useState(false);
  const { run, busy } = useAction();
  const canEdit = allows(workspace, "account_manager", "finance", "legal");

  if (loading) return <Loading rows={8} />;
  if (error) return <ErrorBox error={error} retry={reload} />;

  return (
    <>
      <PageHead title={c.name} sub={<>{label(c.kind)} · <Chip status={c.status} />{c.inactive_since && ` since ${date(c.inactive_since)} — ${c.inactive_reason ?? ""}`}</>}
        actions={<>
          <button className="btn" onClick={() => router.back()}>Back</button>
          {canEdit && <button className="btn" onClick={() => setEditing(true)}>Edit</button>}
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
            <dt>Contact</dt><dd>{c.contact_name ?? "–"} {c.contact_email && <a href={`mailto:${c.contact_email}`}>{c.contact_email}</a>}</dd>
            <dt>Phone</dt><dd>{c.contact_phone ?? "–"}</dd>
            <dt>State</dt><dd>{c.state ?? "–"}</dd>
            <dt>EIN</dt><dd>{c.ein ?? <span className="masked">••••</span>}</dd>
            <dt>Payment terms</dt><dd>{c.default_terms}</dd>
            <dt>Bank verified</dt><dd>{c.bank_verified ? "Yes" : "No"}</dd>
            {c.balances && <><dt>Open AR</dt><dd>{money(c.balances.open_ar)}</dd><dt>Open AP</dt><dd>{money(c.balances.open_ap)}</dd></>}
          </dl>
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
      {c.documents.length > 0 && (
        <div className="card mt">
          <h3>Tracked documents</h3>
          {c.documents.map((d: any) => <div key={d.id} className="alert"><Chip status={d.status} /><b>{d.label}</b> {d.expires_on && `· expires ${date(d.expires_on)}`} {d.blocks && `· blocks ${d.blocks}`}</div>)}
        </div>
      )}
      <Attachments ownerType="company" ownerId={id} canEdit={canEdit} />
      {editing && <Modal title={`Edit ${c.name}`} onClose={() => setEditing(false)}><CompanyForm initial={c} onSaved={() => { setEditing(false); reload(); }} /></Modal>}
    </>
  );
}
