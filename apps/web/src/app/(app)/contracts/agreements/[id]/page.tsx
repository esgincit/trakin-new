"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Acceptance } from "@/components/Acceptance";
import { Attachments } from "@/components/Attachments";
import { Bar, Chip, ErrorBox, Loading, PageHead } from "@/components/ui";
import { date, label } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

export default function AgreementDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { workspace } = useSession();
  const { data: a, error, loading, reload } = useApi(`/agreements/${id}`);
  if (loading) return <Loading rows={6} />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  const canEdit = allows(workspace, "legal", "account_manager", "finance", "hr");
  return (
    <>
      <PageHead title={`${a.code} · ${label(a.kind)}`} sub={<>{a.counterparty} · <Chip status={a.status} /> · {a.source === "myTrakIn" ? "Created in myTrakIn" : `Recorded (${a.source})`}</>}
        actions={<>
          <button className="btn" onClick={() => router.back()}>Back</button>
          {canEdit && ["draft", "active"].includes(a.status) && <Link className="btn pri" href={`/esign/new?agreement_id=${id}&title=${encodeURIComponent(`${label(a.kind)} ${a.code}`)}`}>Send for signature</Link>}
        </>} />
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
          {a.envelopes.map((e: any) => <div key={e.id} className="alert click" onClick={() => router.push(`/esign/${e.id}`)}><Chip status={e.status} />{e.number} · {e.title}</div>)}
          {!a.envelopes.length && <p className="muted">Not sent for e-signature in myTrakIn.</p>}
        </div>
      </div>
      <Acceptance entityType="agreement" entityId={id} canRecord={allows(workspace, "legal", "account_manager") && a.status !== "active"} onRecorded={reload} />
      <Attachments ownerType="agreement" ownerId={id} canEdit={canEdit} />
    </>
  );
}
