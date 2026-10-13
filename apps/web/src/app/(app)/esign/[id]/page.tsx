"use client";

import { useParams, useRouter } from "next/navigation";
import { Chip, ErrorBox, Loading, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime, label } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

export default function EnvelopeDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { workspace } = useSession();
  const { data: env, error, loading, reload } = useApi(`/envelopes/${id}`);
  const { run, busy } = useAction();
  if (loading) return <Loading rows={6} />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  const canSend = allows(workspace, "legal", "account_manager", "finance", "hr");

  const open = async () => {
    const r = await run(() => api(`/envelopes/${id}/download`));
    if (r) window.open(r.url, "_blank", "noopener");
  };

  return (
    <>
      <PageHead title={`${env.number} · ${env.title}`} sub={<><Chip status={env.status} /> · sent by {env.sent_by_name ?? "–"} {env.sent_at && `on ${dateTime(env.sent_at)}`}</>}
        actions={<>
          <button className="btn" onClick={() => router.back()}>Back</button>
          <button className="btn" onClick={open}>{env.status === "completed" ? "Download signed PDF" : "View document"}</button>
          {canSend && env.status === "draft" && <button className="btn pri" disabled={busy} onClick={async () => { if (await run(() => api(`/envelopes/${id}/send`, { method: "POST" }), "Sent")) reload(); }}>Send</button>}
          {canSend && env.status === "sent" && <button className="btn" disabled={busy} onClick={async () => { if (await run(() => api(`/envelopes/${id}/remind`, { method: "POST" }), "Reminder sent")) reload(); }}>Remind now</button>}
          {canSend && ["draft", "sent"].includes(env.status) && <button className="btn" disabled={busy} onClick={async () => {
            const reason = prompt("Why are you voiding this envelope?");
            if (reason && await run(() => api(`/envelopes/${id}/void`, { body: { reason } }), "Voided")) reload();
          }}>Void</button>}
        </>} />
      <div className="grid c2">
        <div className="card">
          <h3>Signers</h3>
          {env.signers.map((s: any) => (
            <div key={s.id} className="alert">
              <Chip status={s.status} />
              <div>
                <b>{s.position}. {s.name}</b>{s.company && ` · ${s.company}`} · {s.email}
                {s.signed_at && <div className="muted" style={{ fontSize: 12.5 }}>Signed {dateTime(s.signed_at)} · IP {s.signed_ip} · {s.signed_user_agent} · {s.signed_location ?? "location unknown"} · {s.signature_type}</div>}
                {s.declined_reason && <div className="err">Declined: {s.declined_reason}</div>}
              </div>
            </div>
          ))}
          <p className="note">Document fingerprint (SHA-256): <code style={{ wordBreak: "break-all" }}>{env.document_sha256}</code></p>
          {env.signed_sha256 && <p className="note">Sealed PDF fingerprint: <code style={{ wordBreak: "break-all" }}>{env.signed_sha256}</code></p>}
        </div>
        <div className="card">
          <h3>Audit trail</h3>
          <div className="timeline">
            {env.events.map((e: any, i: number) => (
              <div key={i} className={`ev ${e.event === "signed" || e.event === "completed" ? "good" : e.event === "declined" ? "bad" : ""}`}>
                <b>{label(e.event)}</b>{e.signer && ` · ${e.signer}`}
                <small>{dateTime(e.at)}{e.ip && ` · IP ${e.ip}`}{e.location && ` · ${e.location}`}</small>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
