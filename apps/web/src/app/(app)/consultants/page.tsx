"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { DataButtons } from "@/components/DataButtons";
import { DataTable, type Column } from "@/components/DataTable";
import { Chip, ErrorBox, Field, formValues, ImportButton, Modal, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { allows, canEdit as permits, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

const TABS = [["onboarding", "Onboarding"], ["active", "Active"], ["former", "Former"], ["", "All"]] as const;

const ENGAGEMENTS = [
  { key: "w2_fulltime", title: "W-2 employee (full-time)", text: "Offer letter, I-9, E-Verify, W-4, benefits" },
  { key: "w2_contract", title: "W-2 contract employee", text: "Contract offer, I-9, E-Verify, W-4" },
  { key: "c2c", title: "C2C (through a vendor)", text: "Vendor MSA + SOW, employer handles I-9" },
  { key: "e2e", title: "E2E (employer-to-employer)", text: "Employed by a vendor company; vendor MSA + work order" },
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
    { key: "user_code", label: "ID", value: (r: any) => r.user_code ?? "—" },
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
        actions={allows(workspace, "hr", "account_manager", "legal") && permits(workspace, "consultants") && <>
          <ImportButton entity="consultants" />
          <button className="btn pri" onClick={() => setAdding(true)}>Onboard someone</button>
        </>} />
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
  // The consultant is someone who already has an account somewhere on myTrakIn:
  // search every registered user by name, U-ID or e-mail, and their details come
  // from their profile. They may be new to this workspace.
  const [term, setTerm] = useState("");
  const [found, setFound] = useState<any[]>([]);
  const [looking, setLooking] = useState(false);
  const [person, setPerson] = useState<any>(null);
  const { run, busy } = useAction();

  useEffect(() => {
    if (person) return;
    const q = term.trim();
    if (q.length < 2) { setFound([]); return; }
    let live = true;
    setLooking(true);
    const t = setTimeout(() => {
      api<any[]>("/consultants/candidates", { query: { q } })
        .then((r) => live && setFound(r))
        .catch(() => live && setFound([]))
        .finally(() => live && setLooking(false));
    }, 250);
    return () => { live = false; clearTimeout(t); };
  }, [term, person]);

  const choose = (p: any) => { setPerson(p); setFound([]); setTerm(""); };

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
        if (!person) return alert("Pick the person who is being onboarded");
        const v = formValues(e.currentTarget);
        const body = { user_id: person.user_id, engagement, title: v.title, location: v.location,
                       start_date: v.start_date, employer_company_id: v.employer_company_id || null,
                       skills: v.skills ? v.skills.split(",").map((s: string) => s.trim()).filter(Boolean) : [] };
        const r = await run(() => api("/consultants", { body }), "Onboarding started — they'll get a sign-in invitation");
        if (r) onDone(r.id);
      }}>
        <div className="fields">
          <div className="full">
            <label htmlFor="who">Consultant</label>
            {person ? (
              <div className="row" style={{ marginBottom: 4 }}>
                <div className="ctl" style={{ flex: 1 }}>
                  {person.full_name} <code>{person.user_code ?? "—"}</code>
                  {person.already_consultant > 0 && <span className="muted"> · already a consultant here</span>}
                </div>
                <button type="button" className="btn sm" onClick={() => setPerson(null)}>Change</button>
              </div>
            ) : (
              <>
                <input id="who" className="ctl" autoFocus value={term} placeholder="Name, U-ID or e-mail"
                  onChange={(e) => setTerm(e.target.value)} role="combobox" aria-expanded={found.length > 0}
                  aria-controls="who-list" autoComplete="off" />
                {looking && <p className="note" style={{ marginTop: -6 }}>Searching…</p>}
                {!looking && term.trim().length >= 2 && !found.length && (
                  <p className="note" style={{ marginTop: -6 }}>
                    Nobody matches “{term.trim()}”. The person needs a myTrakIn account somewhere on the platform before they can be onboarded.
                  </p>
                )}
                {found.length > 0 && (
                  <div id="who-list" role="listbox">
                    {found.map((p) => (
                      <button key={p.user_id} type="button" role="option" aria-selected="false" className="alert click"
                        style={{ width: "100%", textAlign: "left" }} onClick={() => choose(p)}>
                        <div>
                          <b>{p.full_name ?? p.email}</b>{" "}
                          <code>{p.user_code ?? "no U-ID"}</code>
                          {p.already_consultant > 0 && <span className="muted"> · already a consultant here</span>}
                          {!p.in_workspace && <span className="muted"> · new to this workspace</span>}
                          <div className="muted" style={{ fontSize: 12.5 }}>{p.email}{p.phone ? ` · ${p.phone}` : ""}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}
            <p className="note" style={{ marginTop: -6 }}>
              Pick anyone registered on myTrakIn — their name, e-mail and mobile come from their profile, and onboarding gives them access here.
            </p>
          </div>
          <Field label="E-mail" name="email" type="email" readOnly value={person?.email ?? ""} placeholder="Filled in when you pick someone" />
          <Field label="Mobile" name="phone" type="tel" readOnly value={person?.phone ?? ""} placeholder="Filled in when you pick someone" />
          <Field label="Start date" name="start_date" type="date" required />
          <Field label="Job title" name="title" />
          <Field label="Work location" name="location" placeholder="City, ST" />
          {(engagement === "c2c" || engagement === "e2e") && (
            <Field label="Employer (vendor)" name="employer_company_id" as="select" required
                   options={[["", "Choose…"], ...(vendors.data ?? []).map((v) => [v.id, v.name] as [string, string])]} full />
          )}
          <Field label="Skills (comma separated)" name="skills" full />
        </div>
        <button className="btn pri mt" disabled={busy || !person}>Start onboarding</button>
      </form>
    </Modal>
  );
}
