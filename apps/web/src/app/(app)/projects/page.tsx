"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { DataButtons } from "@/components/DataButtons";
import { DataTable, type Column } from "@/components/DataTable";
import { ErrorBox, Field, formValues, Modal, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { label, playsRole } from "@/lib/format";
import { allows, canEdit as permits, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

export default function Projects() {
  const router = useRouter();
  const { workspace } = useSession();
  const [tab, setTab] = useState<"projects" | "placements">("projects");
  const projects = useApi<any[]>("/projects");
  const placements = useApi<any[]>(tab === "placements" ? "/placements" : null);
  const [modal, setModal] = useState<"project" | "placement" | null>(null);
  const canEdit = allows(workspace, "account_manager") && permits(workspace, "projects");

  const projectCols: Column<any>[] = [
    { key: "code", label: "Code" }, { key: "name", label: "Project" },
    { key: "client", label: "Client", filter: true }, { key: "prime", label: "Prime vendor", hideSm: true },
    { key: "team_size", label: "Team", type: "number" }, { key: "team", label: "Consultants", hideSm: true },
    { key: "end_date", label: "Ends", type: "date" }, { key: "status", label: "Status", type: "status", filter: true },
  ];
  const placementCols: Column<any>[] = [
    { key: "consultant", label: "Consultant", filter: true }, { key: "project", label: "Project", filter: true },
    { key: "role_title", label: "Role", hideSm: true },
    { key: "ar_company", label: "Bill to (AR)", filter: true }, { key: "bill_rate", label: "Bill rate", type: "money" },
    { key: "ap_payee", label: "Pay to (AP)", value: (r) => r.ap_company ?? r.ap_consultant ?? (r.engagement?.startsWith("w2") ? "Payroll" : "–") },
    { key: "pay_rate", label: "Pay rate", type: "money" },
    { key: "end_date", label: "Ends", type: "date", hideSm: true }, { key: "status", label: "Status", type: "status", filter: true },
  ];

  return (
    <>
      <PageHead title="Projects & placements" sub="A placement puts one consultant on one project with your AR and AP terms. A consultant can have any number of placements."
        actions={canEdit && <>
          <button className="btn" onClick={() => setModal("project")}>New project</button>
          <button className="btn pri" onClick={() => setModal("placement")}>New placement</button>
        </>} />
      <div className="tabs">
        <button className={tab === "projects" ? "on" : ""} onClick={() => setTab("projects")}>Projects</button>
        <button className={tab === "placements" ? "on" : ""} onClick={() => setTab("placements")}>Placements</button>
      </div>
      {tab === "projects" ? (
        <><ErrorBox error={projects.error} retry={projects.reload} />
          <DataTable id="projects" rows={projects.data} columns={projectCols} onRowClick={(r) => router.push(`/projects/${r.id}`)} toolbar={<DataButtons entity="projects" label="projects" />} /></>
      ) : (
        <><ErrorBox error={placements.error} retry={placements.reload} />
          <DataTable id="placements" rows={placements.data} columns={placementCols} onRowClick={(r) => router.push(`/projects/${r.project_id}`)} toolbar={<DataButtons entity="placements" label="placements" />} />
          <p className="note">Only the two rates you are party to are stored: what you bill your customer and what you pay your vendor or contractor. The end client's rate is never recorded.</p></>
      )}
      {modal === "project" && <ProjectModal onClose={() => setModal(null)} onDone={(p) => router.push(`/projects/${p.id}`)} />}
      {modal === "placement" && <PlacementModal onClose={() => setModal(null)} onDone={() => { setModal(null); setTab("placements"); placements.reload(); }} />}
    </>
  );
}

function ProjectModal({ onClose, onDone }: { onClose: () => void; onDone: (p: any) => void }) {
  const companies = useApi<any[]>("/companies");
  // T011303-1049: companies we have an MSA with live in their own workspace, so they aren't in /companies.
  const partners = useApi<any[]>("/projects/counterparties");
  const nextCode = useApi<{ code: string }>("/projects/next-code");
  const { run, busy } = useAction();
  const opts = (kinds: string[]) => {
    const own = (companies.data ?? []).filter((c) => playsRole(c, ...kinds));
    const msa = (partners.data ?? []).filter((p) => !own.some((c) => c.id === p.id));
    return [["", "–"] as [string, string], ...[...own, ...msa].map((c) => [c.id, c.name] as [string, string])];
  };
  return (
    <Modal title="New project" onClose={onClose}>
      <form className="form" onSubmit={async (e) => { e.preventDefault(); const r = await run(() => api("/projects", { body: formValues(e.currentTarget) }), "Project created"); if (r) onDone(r); }}>
        <div className="fields">
          <Field label="Code (auto-assigned)" name="code" required readOnly defaultValue={nextCode.data?.code} key={nextCode.data?.code ?? "loading"} />
          <Field label="Name" name="name" required />
          <Field label="Client (end client)" name="client_company_id" as="select" options={opts(["client", "end_client"])} />
          <Field label="Prime vendor (if you're a sub)" name="prime_company_id" as="select" options={opts(["prime_vendor"])} />
          <Field label="Start" name="start_date" type="date" />
          <Field label="End" name="end_date" type="date" />
          <Field label="Status" name="status" as="select"
                 options={[["active", "Active"], ["planned", "Planned (NDA / MSA not signed yet)"], ["internal", "Internal"]]} />
          <Field label="Client timesheet approver" name="client_approver" full />
          <Field label="Description" name="description" as="textarea" full />
        </div>
        <button className="btn pri mt" disabled={busy}>Create project</button>
      </form>
    </Modal>
  );
}

function PlacementModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const consultants = useApi<any[]>("/consultants");
  const projects = useApi<any[]>("/projects");
  const shared = useApi<any[]>("/projects/shared");
  const companies = useApi<any[]>("/companies");
  const partners = useApi<any[]>("/projects/counterparties");
  const sows = useApi<any[]>("/sows");
  const [consultantId, setConsultantId] = useState("");
  const { run, busy } = useAction();
  const consultant = consultants.data?.find((c) => c.id === consultantId);
  const [projectId, setProjectId] = useState("");
  const projClient = projects.data?.find((p) => p.id === projectId)?.client
    ?? shared.data?.find((p) => p.id === projectId)?.client;
  const pick = (rows: any[] | undefined, f: (r: any) => boolean, lbl: (r: any) => string) => [["", "–"] as [string, string], ...(rows ?? []).filter(f).map((r) => [r.id, lbl(r)] as [string, string])];
  // Our companies in that role, plus the companies we have an MSA with (they live in their own workspace).
  const orMsa = (...kinds: string[]) => (c: any) => playsRole(c, ...kinds) || (partners.data ?? []).some((p) => p.id === c.id);
  const parties = [...(companies.data ?? []), ...(partners.data ?? []).filter((p) => !companies.data?.some((c) => c.id === p.id))];

  return (
    <Modal title="New placement" onClose={onClose}>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        const v: any = formValues(e.currentTarget);
        for (const k of ["bill_rate", "pay_rate", "hours_per_week"]) if (v[k]) v[k] = Number(v[k]);
        v.pay_when_paid = v.pay_when_paid === "yes";
        if (await run(() => api("/placements", { body: v }), "Placement created")) onDone();
      }}>
        <div className="fields">
          <Field label="Consultant" name="consultant_id" as="select" required value={consultantId} onChange={(e: any) => setConsultantId(e.target.value)}
                 options={pick(consultants.data, (c) => c.status !== "former", (c) => `${c.full_name} (${label(c.engagement)})`)} />
          {/* Our live projects, plus ones another company assigned to us by SOW (our copy is made on save). */}
          <Field label="Project" name="project_id" as="select" required value={projectId} onChange={(e: any) => setProjectId(e.target.value)}
                 options={[...pick(projects.data, (p) => p.status !== "completed", (p) => `${p.code} · ${p.name}`),
                   ...(shared.data ?? []).filter((p) => !p.local_project_id).map((p) => [p.id, `${p.code} · ${p.name} (from ${p.assigned_by})`] as [string, string])]} />
          {projectId && (
            <div className="full"><label>End client</label><div className="ctl">{projClient ?? "—"}</div></div>
          )}
          <Field label="Role" name="role_title" />
          <Field label="Hours per week" name="hours_per_week" type="number" defaultValue="40" min="1" max="80" />
          <Field label="Start" name="start_date" type="date" required />
          <Field label="End" name="end_date" type="date" />
          <Field label="Bill to (AR customer)" name="ar_company_id" as="select" options={pick(parties, orMsa("client", "prime_vendor"), (c) => c.name)} />
          <Field label="AR SOW / work order" name="ar_sow_id" as="select" options={pick(sows.data, (s) => s.side === "we_bill", (s) => `${s.code} · ${s.counterparty}`)} />
          <Field label="Bill rate ($/h)" name="bill_rate" type="number" step="0.01" min="0" />
          <Field label="AR terms" name="ar_terms" placeholder="Net 30" />
          {["c2c", "e2e"].includes(consultant?.engagement) &&<Field label="Pay to (vendor)" name="ap_company_id" as="select" options={pick(parties, orMsa("vendor"), (c) => c.name)} />}
          {consultant && !consultant.engagement.startsWith("w2") && <>
            <Field label="AP SOW / work order" name="ap_sow_id" as="select" options={pick(sows.data, (s) => s.side === "we_pay", (s) => `${s.code} · ${s.counterparty}`)} />
            <Field label="Pay rate ($/h)" name="pay_rate" type="number" step="0.01" min="0" />
            <Field label="AP terms" name="ap_terms" placeholder="Net 30" />
            <Field label="Pay when paid" name="pay_when_paid" as="select" options={[["no", "No"], ["yes", "Yes — pay after the customer pays"]]} />
          </>}
        </div>
        {consultant?.engagement.startsWith("w2") && <p className="note">W-2 employees are paid through payroll, so there is no AP payee.</p>}
        <button className="btn pri mt" disabled={busy}>Create placement</button>
      </form>
    </Modal>
  );
}
