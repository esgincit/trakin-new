"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Attachments } from "@/components/Attachments";
import { Bar, Chip, ErrorBox, Loading, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, label } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { workspace } = useSession();
  const { data: p, error, loading, reload } = useApi(`/projects/${id}`);
  const { run, busy } = useAction();
  if (loading) return <Loading rows={6} />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  return (
    <>
      <PageHead title={`${p.code} · ${p.name}`} sub={<>{p.client ?? "Internal"}{p.prime && ` via ${p.prime}`} · <Chip status={p.status} /> · {date(p.start_date)} – {date(p.end_date)}</>}
        actions={<>
          <button className="btn" onClick={() => router.back()}>Back</button>
          {p.status === "planned" && allows(workspace, "account_manager") && (
            <button className="btn pri" disabled={busy} onClick={async () => {
              const body = { code: p.code, name: p.name, client_company_id: p.client_company_id, prime_company_id: p.prime_company_id,
                             description: p.description, start_date: p.start_date, end_date: p.end_date,
                             client_approver: p.client_approver, status: "active" };
              if (await run(() => api(`/projects/${id}`, { method: "PATCH", body }), "Project activated")) reload();
            }}>Activate project</button>
          )}
        </>} />
      {p.description && <p>{p.description}</p>}
      <div className="grid c2">
        <div className="card">
          <h3>Team</h3>
          {p.team.map((t: any) => (
            <div key={t.placement_id} className="alert">
              <Chip status={t.status} />
              <div style={{ flex: 1 }}><Link href={`/consultants/${t.consultant_id}`}>{t.full_name}</Link> · {t.role_title}
                <div className="muted" style={{ fontSize: 12.5 }}>{label(t.engagement)} · {Number(t.hours_per_week)} h/week · {date(t.start_date)} – {date(t.end_date)}</div></div>
              <Chip status={t.this_week ?? "not_submitted"}>This week: {label(t.this_week ?? "not submitted")}</Chip>
            </div>
          ))}
          {!p.team.length && <p className="muted">No one placed yet.</p>}
        </div>
        <div className="card">
          <h3>SOWs</h3>
          {p.sows.map((s: any) => (
            <div key={s.id} className="alert click" onClick={() => router.push(`/contracts/sows/${s.id}`)}>
              <div style={{ flex: 1 }}><b>{s.code}</b> {s.title}<div className="muted" style={{ fontSize: 12.5 }}>Ends {date(s.end_date)}</div></div>
              <div style={{ width: 90 }}><Bar pct={s.burn_pct} /></div>
            </div>
          ))}
          <dl className="dl mt"><dt>Client approver</dt><dd>{p.client_approver ?? "–"}</dd></dl>
        </div>
      </div>
      <Attachments ownerType="project" ownerId={id} canEdit={allows(workspace, "account_manager")} />
    </>
  );
}
