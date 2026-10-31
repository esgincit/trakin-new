"use client";

import { Chip, ErrorBox, Loading, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, dateTime, effectiveStatus, label } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function MyDocuments() {
  const { data, error, loading, reload } = useApi("/me/consultant");
  const { run, busy } = useAction();
  if (loading) return <Loading rows={6} />;
  if (error) return <ErrorBox error={error} retry={reload} />;

  const openPolicy = async (id: string) => {
    const r = await run(() => api(`/policies/${id}/file`));
    if (r) window.open(r.url, "_blank", "noopener");
  };

  return (
    <>
      <PageHead title="Policies & documents" sub="Company policies to read and accept, your signed agreements, and the documents we track for you." />
      <div className="card">
        <h3>Company policies</h3>
        {data.policies.map((p: any) => (
          <div key={p.id} className="alert">
            <Chip status={p.accepted_at ? "accepted" : "pending"}>{p.accepted_at ? "Accepted" : "To accept"}</Chip>
            <div style={{ flex: 1 }}><b>{p.name}</b> {p.version}<div className="muted" style={{ fontSize: 12.5 }}>Effective {date(p.effective_on)}{p.accepted_at && ` · accepted ${dateTime(p.accepted_at)}`}</div></div>
            <button className="btn sm" onClick={() => openPolicy(p.id)}>Read</button>
            {!p.accepted_at && (
              <button className="btn sm pri" disabled={busy} onClick={async () => {
                if (confirm(`I have read and agree to follow "${p.name} ${p.version}".`) &&
                    await run(() => api(`/me/policies/${p.id}/accept`, { body: { confirm: true } }), "Thank you — recorded with the time and your IP address")) reload();
              }}>Accept</button>
            )}
          </div>
        ))}
        {!data.policies.length && <p className="muted">No policies apply to you yet.</p>}
      </div>
      <div className="grid c2 mt">
        <div className="card">
          <h3>My agreements and offers</h3>
          {data.agreements.length ? data.agreements.map((a: any) => (
            <div key={a.id} className="alert"><Chip status={effectiveStatus(a)} /><div><b>{label(a.kind)}</b> {a.code}<div className="muted" style={{ fontSize: 12.5 }}>{date(a.effective_on)} – {date(a.expires_on)}</div></div></div>
          )) : <p className="muted">Agreements signed with you (NDA, offer letter, contractor agreement) appear here.</p>}
        </div>
        <div className="card">
          <h3>Documents we track</h3>
          {data.documents.length ? data.documents.map((d: any) => (
            <div key={d.id} className="alert"><Chip status={d.status} /><div><b>{d.label}</b><div className="muted" style={{ fontSize: 12.5 }}>{d.expires_on ? `Expires ${date(d.expires_on)}` : "No expiry"}</div></div></div>
          )) : <p className="muted">Nothing tracked.</p>}
          <p className="note">You get e-mail reminders 120, 90, 60, 30, 14 and 7 days before a document expires. Send the renewed document to HR.</p>
        </div>
      </div>
    </>
  );
}
