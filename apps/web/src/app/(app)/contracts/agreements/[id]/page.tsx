"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Acceptance } from "@/components/Acceptance";
import { Attachments } from "@/components/Attachments";
import { Bar, Chip, ErrorBox, Field, Loading, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, effectiveStatus, label, AGREEMENT_TERMS } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

const MASTER = ["msa", "subcontract"];

/** The company an MSA was sent to accepts it (it comes into force) or rejects it with a note. */
function RespondPanel({ id, onDone }: { id: string; onDone: () => void }) {
  const { run, busy } = useAction();
  const [note, setNote] = useState("");
  return (
    <div className="card mt">
      <h3>Accept this MSA?</h3>
      <p className="muted">The sending company wants this MSA in place with you. Accepting brings it into force; rejecting sends it back with your reason.</p>
      <Field label="Note (required to reject)" name="note" as="textarea" value={note} onChange={(e: any) => setNote(e.target.value)} full />
      <div className="row mt">
        <button className="btn pri" disabled={busy} onClick={async () => {
          if (await run(() => api(`/agreements/${id}/respond`, { body: { decision: "accept", note: note.trim() || undefined } }), "MSA accepted")) onDone();
        }}>Accept MSA</button>
        <button className="btn" disabled={busy || !note.trim()} onClick={async () => {
          if (await run(() => api(`/agreements/${id}/respond`, { body: { decision: "reject", note: note.trim() } }), "MSA rejected")) onDone();
        }}>Reject with note</button>
      </div>
    </div>
  );
}

/** Renewal requests: either company asks; the other accepts (end date moves) or declines with a note. */
function Renewals({ id, a, mySide, onDone }: { id: string; a: any; mySide: string; onDone: () => void }) {
  const { run, busy } = useAction();
  const [expires, setExpires] = useState("");
  const [note, setNote] = useState("");
  const canRequest = MASTER.includes(a.kind) && ["accepted", "active", "expired"].includes(a.status);
  return (
    <div className="card mt">
      <h3>Renewal</h3>
      {a.status === "expired" && <p className="err" style={{ marginTop: 0 }}>This MSA expired on {date(a.expires_on)}. Request a renewal to put a new end date on it.</p>}
      {(a.renewals ?? []).map((r: any) => (
        <div key={r.id} className="alert">
          <Chip status={r.status} />
          <div style={{ flex: 1 }}>
            <b>Renew until {date(r.proposed_expires_on)}</b> · requested by {r.requested_by_name ?? "the other company"} on {date(r.requested_on)}
            {r.note && <div className="muted" style={{ fontSize: 12.5 }}>Note: {r.note}</div>}
            {r.decision_note && <div className="muted" style={{ fontSize: 12.5 }}>Answer: {r.decision_note}</div>}
            {r.status === "pending" && r.requested_side !== mySide && <RenewalAnswer renewalId={r.id} disabledBusy={busy} onDone={onDone} />}
          </div>
        </div>
      ))}
      {!(a.renewals ?? []).length && <p className="muted">No renewal requests yet.</p>}
      {canRequest && !(a.renewals ?? []).some((r: any) => r.status === "pending") && (
        <div className="form mt">
          <div className="fields">
            <Field label="New end date" name="expires_on" type="date" value={expires} onChange={(e: any) => setExpires(e.target.value)} />
            <Field label="Note for the other company" name="note" as="textarea" value={note} onChange={(e: any) => setNote(e.target.value)} full />
          </div>
          <button className="btn pri" disabled={busy || !expires} onClick={async () => {
            if (await run(() => api(`/agreements/${id}/renewals`, { body: { expires_on: expires, note: note.trim() || undefined } }), "Renewal requested")) {
              setExpires(""); setNote(""); onDone();
            }
          }}>Request renewal</button>
        </div>
      )}
    </div>
  );
}

function RenewalAnswer({ renewalId, disabledBusy, onDone }: { renewalId: string; disabledBusy: boolean; onDone: () => void }) {
  const { run, busy } = useAction();
  const [note, setNote] = useState("");
  return (
    <div className="mt">
      <Field label="Note (required to decline)" name={`answer-${renewalId}`} as="textarea" value={note} onChange={(e: any) => setNote(e.target.value)} full />
      <div className="row mt">
        <button className="btn pri sm" disabled={busy || disabledBusy} onClick={async () => {
          if (await run(() => api(`/agreements/renewals/${renewalId}/respond`, { body: { decision: "accept", note: note.trim() || undefined } }), "Renewal accepted")) onDone();
        }}>Accept renewal</button>
        <button className="btn sm" disabled={busy || disabledBusy || !note.trim()} onClick={async () => {
          if (await run(() => api(`/agreements/renewals/${renewalId}/respond`, { body: { decision: "decline", note: note.trim() } }), "Renewal declined")) onDone();
        }}>Decline with note</button>
      </div>
    </div>
  );
}

export default function AgreementDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { workspace } = useSession();
  const { data: a, error, loading, reload } = useApi(`/agreements/${id}`);
  const { run, busy } = useAction();
  const [editing, setEditing] = useState(false);
  const [editValues, setEditValues] = useState<Record<string, any>>({});
  const startEditing = () => {
    // Seed the form from the saved agreement; a plain object created during render
    // would be wiped by the re-render that opens the form.
    setEditValues({
      effective_on: a.effective_on ?? "",
      expires_on: a.expires_on ?? "",
      payment_terms: a.payment_terms ?? "",
      renewal: a.renewal ?? "",
      notice_period: a.notice_period ?? "",
      insurance_required: a.insurance_required ?? "",
      tenant_side: a.tenant_side ?? "",
    });
    setEditing(true);
  };
  const setField = (key: string, value: any) => setEditValues((cur) => ({ ...cur, [key]: value }));
  // A document sent for signature lives with its envelope, not in this agreement's
  // files — open it from there rather than duplicating the upload.
  const openDocument = async (envelopeId: string, doc: any) => {
    const r = await run(() => api(`/envelopes/${envelopeId}/documents/${doc.id}/download`));
    if (r?.url) window.open(r.url, "_blank", "noopener");
  };
  if (loading) return <Loading rows={6} />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  // A shared agreement belongs to the workspace that recorded it: read-only here.
  const shared = !!a.shared;
  const canEdit = allows(workspace, "legal", "account_manager", "finance", "hr") && !shared;
  return (
    <>
      <PageHead title={`${a.code} · ${label(a.kind)}`} sub={<>{shared ? `Received from ${a.sent_by_company ?? "the other company"}` : a.counterparty} · <Chip status={effectiveStatus(a)} /> · {shared ? "Sent to your company" : a.source === "myTrakIn" ? "Created in myTrakIn" : `Recorded (${a.source})`}</>}
        actions={<> 
          <button className="btn" onClick={() => router.back()}>Back</button>
          {canEdit && a.status === "draft" && <button className="btn" onClick={startEditing}>Edit</button>}
          {canEdit && a.status === "draft" && <Link className="btn pri" href={`/esign/new?agreement_id=${id}&title=${encodeURIComponent(`${label(a.kind)} ${a.code}`)}`}>Send for signature</Link>}
        </>} />
      {editing ? (
        <div className="grid c2">
          <div className="card">
            <h3>Edit agreement</h3>
            <form className="form" onSubmit={async (e) => {
              e.preventDefault();
              const updates: any = {};
              for (const k of ["effective_on", "expires_on", "payment_terms", "renewal", "notice_period", "insurance_required", "tenant_side"]) {
                if (editValues[k] !== undefined && editValues[k] !== null && editValues[k] !== "") updates[k] = editValues[k];
              }
              if (Object.keys(updates).length === 0) {
                setEditing(false);
                return;
              }
              if (await run(() => api(`/agreements/${id}`, { method: "PATCH", body: updates }), "Agreement updated")) {
                setEditing(false);
                reload();
              }
            }}>
              <div className="fields">
                <Field label="Effective" name="effective_on" type="date" required value={editValues.effective_on ?? ""} onChange={(e: any) => setField("effective_on", e.target.value)} />
                <Field label="Expires" name="expires_on" type="date" value={editValues.expires_on ?? ""} onChange={(e: any) => setField("expires_on", e.target.value)} />
                <Field label="Payment terms" name="payment_terms" as="select" options={AGREEMENT_TERMS.payment_terms} value={editValues.payment_terms ?? ""} onChange={(e: any) => setField("payment_terms", e.target.value)} />
                <Field label="Renewal" name="renewal" as="select" options={AGREEMENT_TERMS.renewal} value={editValues.renewal ?? ""} onChange={(e: any) => setField("renewal", e.target.value)} />
                <Field label="Notice period" name="notice_period" as="select" options={AGREEMENT_TERMS.notice_period} value={editValues.notice_period ?? ""} onChange={(e: any) => setField("notice_period", e.target.value)} />
                <Field label="Insurance required" name="insurance_required" as="select" options={AGREEMENT_TERMS.insurance_required} value={editValues.insurance_required ?? ""} onChange={(e: any) => setField("insurance_required", e.target.value)} />
                <Field label="You are the" name="tenant_side" as="select" options={[["supplier", "Supplier"], ["buyer", "Buyer"], ["employer", "Employer"]]} value={editValues.tenant_side ?? ""} onChange={(e: any) => setField("tenant_side", e.target.value)} />
              </div>
              <div className="row mt">
                <button className="btn pri" disabled={busy}>Save</button>
                <button className="btn" onClick={() => setEditing(false)}>Cancel</button>
              </div>
            </form>
          </div>
        </div>
      ) : (
        <div className="grid c2">
          <div className="card">
            <dl className="dl">
              <dt>With</dt><dd>{a.counterparty}</dd>
              <dt>You are</dt><dd>{label(a.tenant_side)}</dd>
              <dt>Effective</dt><dd>{date(a.effective_on)}</dd>
              <dt>Expires</dt><dd>{date(a.expires_on)}</dd>
              <dt>Payment terms</dt><dd>{a.payment_terms ?? "–"}</dd>
              <dt>Renewal</dt><dd>{a.renewal ?? "–"}</dd>
              <dt>Notice</dt><dd>{a.notice_period ?? "–"}</dd>
              <dt>Insurance</dt><dd>{a.insurance_required ?? "–"}</dd>
              <dt>Signed by</dt><dd>{a.signed_by ?? "–"}</dd>
            </dl>
          </div>
          <div className="card">
            <h3>SOWs under this agreement</h3>
            {a.sows.map((s: any) => (
              <div key={s.id} className="alert click" onClick={() => router.push(`/contracts/sows/${s.id}`)}>
                <div style={{ flex: 1 }}><b>{s.code}</b> {s.title}<div className="muted" style={{ fontSize: 12.5 }}>Ends {date(s.end_date)}</div></div>
                <div style={{ width: 90 }}><Bar pct={s.burn_pct} /></div>
              </div>
            ))}
            {!a.sows.length && <p className="muted">None yet.</p>}
            <h3 className="mt">Signatures</h3>
            {a.envelopes.map((e: any) => (
              <div key={e.id} className="alert">
                <div className="alert click" onClick={() => router.push(`/esign/${e.id}`)}>
                  <Chip status={e.status} />{e.number} · {e.title}
                </div>
                {e.documents?.length > 0 && (
                  <div className="mt" style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    <span className="muted" style={{ fontSize: 12.5, alignSelf: "center" }}>
                      {e.documents.length > 1 ? `${e.documents.length} documents:` : "Document:"}
                    </span>
                    {e.documents.map((d: any) => (
                      <button key={d.id} className="btn sm" onClick={() => openDocument(e.id, d)}>
                        📄 {d.name}{d.size_bytes != null ? ` · ${Math.ceil(d.size_bytes / 1024)} KB` : ""}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {!a.envelopes.length && <p className="muted">Not sent for e-signature in myTrakIn.</p>}
          </div>
        </div>
      )}
      {MASTER.includes(a.kind) && a.status === "rejected" && (
        <p className="err" role="alert">Rejected{a.decision_note ? <>: “{a.decision_note}”</> : ""}. Send a corrected MSA to reopen it.</p>
      )}
      {!shared && MASTER.includes(a.kind) && a.status === "pending" && (
        <p className="note">Waiting for {a.counterparty} to accept or reject this MSA. It isn&apos;t in force until they accept.</p>
      )}
      {shared && a.status === "pending" && <RespondPanel id={id} onDone={reload} />}
      {MASTER.includes(a.kind) && <Renewals id={id} a={a} mySide={shared ? "counterparty" : "sender"} onDone={reload} />}
      <Acceptance entityType="agreement" entityId={id} canRecord={allows(workspace, "legal", "account_manager") && !["active", "accepted"].includes(a.status) && !shared} onRecorded={reload} active={["active", "accepted"].includes(a.status)} />
      <Attachments ownerType="agreement" ownerId={id} canEdit={canEdit} />
    </>
  );
}
