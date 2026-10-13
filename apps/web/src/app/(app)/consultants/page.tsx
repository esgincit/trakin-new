"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { DataButtons } from "@/components/DataButtons";
import { DataTable, type Column } from "@/components/DataTable";
import { Chip, ErrorBox, Field, formValues, Modal, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

const TABS = [["onboarding", "Onboarding"], ["active", "Active"], ["former", "Former"], ["", "All"]] as const;

const ENGAGEMENTS = [
  { key: "w2_fulltime", title: "W-2 employee (full-time)", text: "Offer letter, I-9, E-Verify, W-4, benefits" },
  { key: "w2_contract", title: "W-2 contract employee", text: "Contract offer, I-9, E-Verify, W-4" },
  { key: "c2c", title: "C2C (through a vendor)", text: "Vendor MSA + SOW, employer handles I-9" },
  { key: "1099", title: "1099 independent contractor", text: "Contractor agreement, W-9, classification review" },
];

export default function ConsultantsPage() {
  return <Suspense><Consultants /></Suspense>;
}

function Consultants() {
  const router = useRouter();
  const params = useSearchParams();
  const { workspace } = useSession();
  const [tab, setTab] = useState<string>(params.get("tab") ?? "active");
  const { data, error, reload } = useApi<any[]>("/consultants", { status: tab || undefined });
  const [adding, setAdding] = useState(false);

  const columns: Column<any>[] = [
    { key: "full_name", label: "Name" },
    { key: "engagement", label: "Type", type: "label", filter: true },
    { key: "title", label: "Title", hideSm: true },
    { key: "employer", label: "Employer (C2C)", filter: true, hideSm: true },
    { key: "projects", label: "Projects" },
    ...(tab === "onboarding" ? [{ key: "checklist", label: "Checklist", value: (r: any) => `${r.checklist_done}/${r.checklist_total}` }] : []),
    ...(tab === "former" ? [{ key: "end_date", label: "Left", type: "date" as const }, { key: "leave_reason", label: "Reason" },
      { key: "rehire_eligible", label: "Rehire?", value: (r: any) => (r.rehire_eligible === false ? "No" : "Yes") }] : []),
    { key: "work_auth_expires", label: "Work auth until", type: "date", hideSm: true },
    { key: "location", label: "Location", filter: true, hideSm: true },
    { key: "status", label: "Status", type: "status" },
  ];

  return (
    <>
      <PageHead title="Consultants" sub="W-2 employees, C2C consultants and 1099 contractors — onboarding, active and former. One person can work on any number of projects."
        actions={allows(workspace, "hr", "account_manager", "legal") && <button className="btn pri" onClick={() => setAdding(true)}>Onboard someone</button>} />
      <div className="tabs">
        {TABS.map(([k, t]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{t}</button>)}
      </div>
      <ErrorBox error={error} retry={reload} />
      <DataTable id={`consultants-${tab}`} rows={data} columns={columns} onRowClick={(r) => router.push(`/consultants/${r.id}`)}
                 cardAside={(r) => <Chip status={r.engagement}>{label(r.engagement)}</Chip>} toolbar={<DataButtons entity="consultants" label="consultants" />} />
      {adding && <OnboardModal onClose={() => setAdding(false)} onDone={(id) => router.push(`/consultants/${id}`)} />}
    </>
  );
}

function OnboardModal({ onClose, onDone }: { onClose: () => void; onDone: (id: string) => void }) {
  const [engagement, setEngagement] = useState("w2_contract");
  const vendors = useApi<any[]>("/companies", { kind: "vendor" });
  const { run, busy } = useAction();
  return (
    <Modal title="Onboard a consultant" onClose={onClose}>
      <div className="choice" role="radiogroup" aria-label="Engagement type">
        {ENGAGEMENTS.map((e) => (
          <button key={e.key} type="button" role="radio" aria-checked={engagement === e.key} className={engagement === e.key ? "on" : ""} onClick={() => setEngagement(e.key)}>
            <b>{e.title}</b><small>{e.text}</small>
          </button>
        ))}
      </div>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        const v = formValues(e.currentTarget);
        const body = { ...v, engagement, skills: v.skills ? v.skills.split(",").map((s) => s.trim()).filter(Boolean) : [] };
        const r = await run(() => api("/consultants", { body }), "Onboarding started — they'll get a sign-in invitation");
        if (r) onDone(r.id);
      }}>
        <div className="fields">
          <Field label="Full name" name="full_name" required />
          <Field label="E-mail" name="email" type="email" required />
          <Field label="Mobile" name="phone" type="tel" />
          <Field label="Start date" name="start_date" type="date" required />
          <Field label="Job title" name="title" />
          <Field label="Work location" name="location" placeholder="City, ST" />
          {engagement === "c2c" && (
            <Field label="Employer (vendor)" name="employer_company_id" as="select" required
                   options={[["", "Choose…"], ...(vendors.data ?? []).map((v) => [v.id, v.name] as [string, string])]} full />
          )}
          <Field label="Skills (comma separated)" name="skills" full />
        </div>
        <button className="btn pri mt" disabled={busy}>Start onboarding</button>
      </form>
    </Modal>
  );
}
