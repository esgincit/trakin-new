"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Acceptance } from "@/components/Acceptance";
import { Attachments } from "@/components/Attachments";
import { Bar, Chip, ErrorBox, Field, formValues, Loading, Modal, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, label, money } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

export default function SowDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { workspace } = useSession();
  const { data: s, error, loading, reload } = useApi(`/sows/${id}`);
  const [amending, setAmending] = useState(false);
  const [answering, setAnswering] = useState<"approve" | "reject" | null>(null);
  const { run, busy } = useAction();
  if (loading) return <Loading rows={6} />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  const canEdit = allows(workspace, "legal", "account_manager");
  const shared = !!s.shared;                       // created by another workspace, sent to us
  const awaitingUs = shared && s.status === "pending";
  return (
    <>
      <PageHead title={`${s.code} · ${s.title}`} sub={<>{label(s.side)} · {s.counterparty} · <Chip status={s.status} /> · {date(s.start_date)} – {date(s.end_date)}</>}
        actions={<>
          <button className="btn" onClick={() => router.back()}>Back</button>
          {!shared && canEdit && s.status === "draft" && (
            <button className="btn pri" disabled={busy}
              onClick={async () => { if (await run(() => api(`/sows/${id}/submit`, { method: "POST" }), "Sent to the other company for approval")) reload(); }}>
              Send for approval
            </button>
          )}
          {!shared && canEdit && s.status === "rejected" && (
            <button className="btn" disabled={busy}
              onClick={async () => { if (await run(() => api(`/sows/${id}/submit`, { method: "POST" }), "Sent again for approval")) reload(); }}>
              Send again
            </button>
          )}
          {awaitingUs && (
            <>
              <button className="btn pri" onClick={() => setAnswering("approve")}>Approve</button>
              <button className="btn" onClick={() => setAnswering("reject")}>Turn down</button>
            </>
          )}
          {!shared && canEdit && s.status !== "rejected" && <button className="btn" onClick={() => setAmending(true)}>Amend / extend</button>}
          {!shared && canEdit && s.status === "draft" && <Link className="btn pri" href={`/esign/new?sow_id=${id}&title=${encodeURIComponent(`SOW ${s.code}`)}`}>Send for signature</Link>}
        </>} />
      {awaitingUs && (
        <div className="alert mt">
          <div><b>{s.sent_by} sent you this SOW for approval.</b>
            <div className="muted" style={{ fontSize: 12.5 }}>Under {s.agreement}. Approving puts it into force; turning it down needs a reason.</div></div>
        </div>
      )}
      {s.status === "rejected" && s.decision_note && (
        <div className="alert mt"><div><b>Turned down{s.decision_note && ` — ${s.decision_note}`}</b></div></div>
      )}
      {shared ? (
        <div className="card mt">
          <h3>What {s.sent_by} sent you</h3>
          <dl className="dl">
            <dt>Reference</dt><dd>{s.code}</dd>
            <dt>Title</dt><dd>{s.title}</dd>
            <dt>Under agreement</dt><dd>{s.agreement}</dd>
            <dt>Term</dt><dd>{date(s.start_date)} – {date(s.end_date)}</dd>
            <dt>Status</dt><dd><Chip status={s.status} /></dd>
            <dt>Sent</dt><dd>{s.sent_on ? date(s.sent_on) : "–"}</dd>
          </dl>
          <p className="note">Their value, invoicing and amendments stay in their workspace. This SOW only needs your answer.</p>
        </div>
      ) : (
        <>
      <div className="grid k4">
        <div className="card kpi"><div className="l">Value</div><div className="v">{money(s.value_cap, true)}</div></div>
        <div className="card kpi"><div className="l">Invoiced</div><div className="v">{money(s.invoiced, true)}</div></div>
        <div className="card kpi"><div className="l">Remaining</div><div className="v">{money(s.remaining, true)}</div></div>
        <div className="card kpi"><div className="l">Used</div><div className="v">{s.burn_pct ?? "–"}%</div><Bar pct={s.burn_pct} /></div>
      </div>
      <div className="grid c2 mt">
        <div className="card">
          <dl className="dl">
            <dt>Agreement</dt><dd>{s.agreement}</dd>
            <dt>Consultants</dt><dd>{s.consultants ?? "–"}</dd>
            <dt>Supports</dt><dd>{s.flows_from ?? "–"}</dd>
            <dt>Supported by</dt><dd>{s.flows_to.map((f: any) => f.code).join(", ") || "–"}</dd>
          </dl>
          <h3 className="mt">Amendments</h3>
          {s.amendments.map((a: any) => (
            <div key={a.id} className="alert"><Chip status={a.status} /><div><b>{a.code}</b> {a.summary}
              <div className="muted" style={{ fontSize: 12.5 }}>{a.new_end_date && `New end ${date(a.new_end_date)}`}{a.value_change && ` · ${money(a.value_change)}`}</div></div>
              {canEdit && a.status === "draft" && <Link className="btn sm right" href={`/esign/new?amendment_id=${a.id}&title=${encodeURIComponent(`Amendment ${a.code}`)}`}>Send</Link>}
            </div>
          ))}
          {!s.amendments.length && <p className="muted">No amendments.</p>}
        </div>
        <div className="card">
          <h3>Invoices against this SOW</h3>
          {s.invoices ? (s.invoices.length ? (
            <table><tbody>{s.invoices.map((i: any) => (
              <tr key={i.id} className="click" onClick={() => router.push(`/invoices/${i.id}`)}><td>{i.number}</td><td>{date(i.period_start)}</td><td className="num">{money(i.amount)}</td><td><Chip status={i.live_status} /></td></tr>
            ))}</tbody></table>
          ) : <p className="muted">None yet.</p>) : <p className="muted">Amounts are visible to finance, legal and account managers.</p>}
          <h3 className="mt">Signatures</h3>
          {s.envelopes.map((e: any) => <div key={e.id} className="alert click" onClick={() => router.push(`/esign/${e.id}`)}><Chip status={e.status} />{e.number} · {e.title}</div>)}
        </div>
      </div>
      <Acceptance entityType="sow" entityId={id} canRecord={canEdit && s.status !== "active"} onRecorded={reload} active={s.status === "active"} />
      <Attachments ownerType="sow" ownerId={id} canEdit={canEdit} />
        </>
      )}
      {answering && (
        <Modal title={answering === "approve" ? `Approve ${s.code}?` : `Turn down ${s.code}`} onClose={() => setAnswering(null)}>
          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            const v: any = formValues(e.currentTarget);
            const r = await run(() => api(`/sows/${id}/respond`, { body: { decision: answering, note: v.note } }),
              answering === "approve" ? "Approved — the SOW is in force" : "Turned down — they will see your reason");
            if (r) { setAnswering(null); reload(); }
          }}>
            {answering === "approve"
              ? <p className="muted">{s.sent_by} can now bill or be billed under this SOW.</p>
              : <Field label="Why are you turning it down?" name="note" as="textarea" required
                        placeholder="Budget not agreed for this period" />}
            <button className="btn pri mt" disabled={busy}>{answering === "approve" ? "Approve SOW" : "Turn down"}</button>
          </form>
        </Modal>
      )}
      {amending && (
        <Modal title={`Amend ${s.code}`} onClose={() => setAmending(false)}>
          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            const v: any = formValues(e.currentTarget);
            if (v.value_change) v.value_change = Number(v.value_change);
            if (await run(() => api(`/sows/${id}/amendments`, { body: v }), "Amendment drafted — send it for signature")) { setAmending(false); reload(); }
          }}>
            <Field label="What changes" name="summary" required placeholder="Extend 3 months and add $36,000" />
            <div className="fields">
              <Field label="New end date" name="new_end_date" type="date" />
              <Field label="Value change ($)" name="value_change" type="number" step="0.01" />
            </div>
            <p className="note">The SOW's dates and value change automatically once everyone signs.</p>
            <button className="btn pri mt" disabled={busy}>Draft amendment</button>
          </form>
        </Modal>
      )}
    </>
  );
}
