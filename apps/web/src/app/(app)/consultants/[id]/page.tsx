"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Attachments } from "@/components/Attachments";
import { Chip, ErrorBox, Field, formValues, Loading, Modal, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, dateTime, label } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

export default function ConsultantDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { workspace } = useSession();
  const { data: c, error, loading, reload } = useApi(`/consultants/${id}`);
  const { run, busy } = useAction();
  const [modal, setModal] = useState<"offboard" | "edit" | null>(null);
  const canEdit = allows(workspace, "hr", "account_manager", "legal");
  const hr = allows(workspace, "hr", "legal");

  if (loading) return <Loading rows={8} />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  const done = c.onboarding_checklist.filter((x: any) => x.done).length;
  const allDone = c.onboarding_checklist.length > 0 && done === c.onboarding_checklist.length;

  const toggleAll = async () => {
    if (!canEdit || busy) return;
    const target = !allDone;
    await Promise.all((c.onboarding_checklist ?? []).map((_item: any, i: number) =>
      run(() => api(`/consultants/${id}/checklist`, { body: { index: i, done: target } }))
    ));
    reload();
  };

  return (
    <>
      <PageHead title={c.full_name} sub={<>{c.user_code ? <>ID <code>{c.user_code}</code> · </> : null}{label(c.engagement)}{c.employer && ` via ${c.employer}`} · {c.title ?? ""} · <Chip status={c.status} /></>}
        actions={<>
          <button className="btn" onClick={() => router.back()}>Back</button>
          {canEdit && <button className="btn" onClick={() => setModal("edit")}>Edit</button>}
          {canEdit && c.status === "onboarding" && <button className="btn pri" disabled={busy} onClick={async () => { if (await run(() => api(`/consultants/${id}/activate`, { method: "POST" }), "Active — timesheets are open")) reload(); }}>Finish onboarding</button>}
          {canEdit && c.status === "active" && <button className="btn" onClick={() => setModal("offboard")}>Offboard</button>}
          {canEdit && c.status === "former" && <button className="btn pri" disabled={busy} onClick={async () => { if (await run(() => api(`/consultants/${id}/rehire`, { method: "POST" }), "Rehire started")) reload(); }}>Rehire</button>}
        </>} />

      <div className="grid c2">
        <div className="card">
          <h3>Onboarding checklist · {done}/{c.onboarding_checklist.length}</h3>
          {canEdit && !busy && (
            <div className="row mt" style={{ marginBottom: 8 }}>
              <input type="checkbox" checked={allDone} onChange={toggleAll} />
              <span className="muted" style={{ marginLeft: 6, cursor: "pointer" }} onClick={toggleAll}>
                {allDone ? "Select none" : "Select all"}
              </span>
            </div>
          )}
          {c.onboarding_checklist.map((item: any, i: number) => (
            <label key={i} className="row" style={{ padding: "6px 0", color: "var(--ink)", borderBottom: "1px solid var(--line)" }}>
              <input type="checkbox" checked={item.done} disabled={!canEdit || busy}
                     onChange={async (e) => { if (await run(() => api(`/consultants/${id}/checklist`, { body: { index: i, done: e.target.checked } }))) reload(); }} />
              {item.item}
            </label>
          ))}
        </div>
        <div className="card">
          <h3>Work authorization & I-9</h3>
          <dl className="dl">
            <dt>Type</dt><dd>{c.work_auth_type ?? <span className="muted">HR only</span>}</dd>
            <dt>Valid until</dt><dd>{date(c.work_auth_expires)}</dd>
            <dt>Form I-9</dt><dd>{c.i9_status ?? "–"}</dd>
            <dt>E-Verify</dt><dd>{c.everify_status ?? "–"}</dd>
            <dt>E-mail</dt><dd>{c.email}</dd>
            <dt>Phone</dt><dd>{c.phone ?? "–"}</dd>
            <dt>Started</dt><dd>{date(c.start_date)}{c.end_date && ` · left ${date(c.end_date)} (${c.leave_reason ?? ""})`}</dd>
            <dt>Skills</dt><dd>{c.skills?.join(", ") || "–"}</dd>
          </dl>
        </div>
      </div>

      <div className="grid c2 mt">
        <div className="card">
          <h3>Projects ({c.placements.length})</h3>
          {c.placements.map((p: any) => (
            <div key={p.id} className="alert"><Chip status={p.status} /><div><b>{p.project}</b> · {p.role_title}<div className="muted" style={{ fontSize: 12.5 }}>{date(p.start_date)} – {date(p.end_date)} · {Number(p.hours_per_week)} h/week</div></div></div>
          ))}
          {!c.placements.length && <p className="muted">Not placed yet. Add a placement under Projects.</p>}
          <h3 className="mt">Agreements</h3>
          {c.agreements.map((a: any) => <div key={a.id} className="alert"><Chip status={a.status} /><b>{label(a.kind)}</b> {a.code}</div>)}
          {!c.agreements.length && <p className="muted">No NDA, offer or contractor agreement on file.</p>}
        </div>
        <div className="card">
          <h3>Policies</h3>
          {c.policies.map((p: any, i: number) => (
            <div key={i} className="alert"><Chip status={p.accepted_at ? "accepted" : "pending"}>{p.accepted_at ? "Accepted" : "Pending"}</Chip>
              <div>{p.name} {p.version}{p.accepted_at && <div className="muted" style={{ fontSize: 12.5 }}>{dateTime(p.accepted_at)} · IP {p.ip}</div>}</div></div>
          ))}
          <h3 className="mt">Tracked documents</h3>
          {c.documents.map((d: any) => <div key={d.id} className="alert"><Chip status={d.status} /><b>{d.label}</b>{d.expires_on && ` · expires ${date(d.expires_on)}`}</div>)}
          {!c.documents.length && <p className="muted">Nothing tracked. Add passport, EAD or I-9 reverification dates under Compliance.</p>}
        </div>
      </div>
      <Attachments ownerType="consultant" ownerId={id} canEdit={canEdit} />

      {modal === "offboard" && (
        <Modal title={`Offboard ${c.full_name}`} onClose={() => setModal(null)}>
          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            const v = formValues(e.currentTarget);
            if (await run(() => api(`/consultants/${id}/offboard`, { body: { ...v, rehire_eligible: v.rehire_eligible === "yes" } }), "Moved to Former. All assignments ended; nothing was deleted.")) { setModal(null); reload(); }
          }}>
            <div className="fields">
              <Field label="Last day" name="last_day" type="date" required />
              <Field label="Eligible for rehire" name="rehire_eligible" as="select" options={[["yes", "Yes"], ["no", "No"]]} />
              <Field label="Reason" name="reason" required full placeholder="Resigned, contract ended, project completed…" />
            </div>
            <button className="btn pri mt" disabled={busy}>Offboard</button>
          </form>
        </Modal>
      )}
      {modal === "edit" && (
        <Modal title={`Edit ${c.full_name}`} onClose={() => setModal(null)}>
          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            const v: any = formValues(e.currentTarget);
            if (v.skills) v.skills = v.skills.split(",").map((s: string) => s.trim()).filter(Boolean);
            if (await run(() => api(`/consultants/${id}`, { method: "PATCH", body: v }), "Saved")) { setModal(null); reload(); }
          }}>
            <div className="fields">
              <Field label="Full name" name="full_name" defaultValue={c.full_name} />
              <Field label="E-mail" name="email" type="email" defaultValue={c.email} />
              <Field label="Phone" name="phone" defaultValue={c.phone ?? ""} />
              <Field label="Title" name="title" defaultValue={c.title ?? ""} />
              <Field label="Location" name="location" defaultValue={c.location ?? ""} />
              {hr && <>
                <Field label="Work authorization" name="work_auth_type" defaultValue={c.work_auth_type ?? ""} placeholder="US citizen, H-1B, STEM OPT (EAD)…" />
                <Field label="Valid until" name="work_auth_expires" type="date" defaultValue={c.work_auth_expires ?? ""} />
                <Field label="Form I-9 status" name="i9_status" defaultValue={c.i9_status ?? ""} />
                <Field label="E-Verify status" name="everify_status" defaultValue={c.everify_status ?? ""} />
              </>}
              <Field label="Skills (comma separated)" name="skills" defaultValue={c.skills?.join(", ")} full />
            </div>
            <button className="btn pri mt" disabled={busy}>Save</button>
          </form>
        </Modal>
      )}
    </>
  );
}
