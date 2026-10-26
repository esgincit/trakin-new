"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { DataButtons } from "@/components/DataButtons";
import { DataTable, type Column } from "@/components/DataTable";
import { Bar, Chip, ErrorBox, Field, formValues, ImportButton, Modal, PageHead, useAction } from "@/components/ui";
import { CompanyPicker } from "@/components/CompanyPicker";
import { api } from "@/lib/api";
import { AGREEMENT_TERMS, daysLeft, label } from "@/lib/format";
import { linkFor } from "@/lib/links";
import { allows, canEdit as permits, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

export default function ContractsPage() {
  return <Suspense><Contracts /></Suspense>;
}

function Contracts() {
  const router = useRouter();
  const params = useSearchParams();
  const { workspace } = useSession();
  const [tab, setTab] = useState<"agreements" | "sows" | "missing">((params.get("tab") as any) ?? "agreements");
  const agreements = useApi<any[]>(tab === "agreements" ? "/agreements" : null);
  const sows = useApi<any[]>(tab === "sows" ? "/sows" : null);
  const missing = useApi<any[]>(tab === "missing" ? "/contracts/missing" : null);
  const [modal, setModal] = useState<"agreement" | "sow" | null>(params.get("new") === "agreement" ? "agreement" : null);
  const canEdit = allows(workspace, "legal", "account_manager") && permits(workspace, "contracts");

  const agreementCols: Column<any>[] = [
    { key: "code", label: "ID" }, { key: "kind", label: "Type", type: "label", filter: true },
    { key: "counterparty", label: "With" }, { key: "tenant_side", label: "You are", type: "label", filter: true, hideSm: true },
    { key: "effective_on", label: "Effective", type: "date", hideSm: true }, { key: "expires_on", label: "Expires", type: "date" },
    { key: "days_left", label: "Left", value: (r) => r.days_left, render: (r) => daysLeft(r.days_left) },
    { key: "sow_count", label: "SOWs", type: "number", hideSm: true },
    { key: "source", label: "Source", filter: true, hideSm: true, value: (r) => (r.shared ? "Received" : r.source) },
    { key: "status", label: "Status", type: "status", filter: true },
  ];
  const sowCols: Column<any>[] = [
    { key: "code", label: "SOW", render: (r) => <>{r.code}{r.shared && <Chip status="pending">Sent to you</Chip>}</> },
    { key: "side", label: "Side", type: "label", filter: true },
    { key: "counterparty", label: "With", filter: true }, { key: "consultants", label: "Consultants", hideSm: true },
    { key: "end_date", label: "Ends", type: "date" },
    { key: "value_cap", label: "Value", type: "money", hideSm: true }, { key: "remaining", label: "Remaining", type: "money" },
    { key: "burn_pct", label: "Used", type: "number", render: (r) => <div style={{ minWidth: 90 }}><Bar pct={r.burn_pct} /></div> },
    { key: "flows_from", label: "Supports", hideSm: true }, { key: "latest_amendment", label: "Amendment", hideSm: true },
    { key: "status", label: "Status", type: "status", filter: true },
  ];

  return (
    <>
      <PageHead title="MSAs & SOWs" sub="Master agreements, subcontracts, NDAs, offers and contractor agreements, with the SOWs and work orders under them."
        actions={canEdit && <>
          <ImportButton entity="agreements" label="Import agreement" />
          <button className="btn" onClick={() => setModal("sow")}>Add SOW</button>
          <button className="btn pri" onClick={() => setModal("agreement")}>Add agreement</button>
        </>} />
      <div className="tabs">
        <button className={tab === "agreements" ? "on" : ""} onClick={() => setTab("agreements")}>Agreements</button>
        <button className={tab === "sows" ? "on" : ""} onClick={() => setTab("sows")}>SOWs & work orders</button>
        <button className={tab === "missing" ? "on" : ""} onClick={() => setTab("missing")}>Missing & expiring</button>
      </div>
      {tab === "agreements" && <><ErrorBox error={agreements.error} /><DataTable id="agreements" rows={agreements.data} columns={agreementCols} onRowClick={(r) => router.push(`/contracts/agreements/${r.id}`)} toolbar={<DataButtons entity="agreements" label="agreements" />} /></>}
      {tab === "sows" && <><ErrorBox error={sows.error} /><DataTable id="sows" rows={sows.data} columns={sowCols} onRowClick={(r) => router.push(`/contracts/sows/${r.id}`)} toolbar={<DataButtons entity="sows" label="SOWs" />} /></>}
      {tab === "missing" && <DataTable id="missing" rows={missing.data} onRowClick={(r) => router.push(linkFor(r.ref_type, r.ref_id))} columns={[
        { key: "tone", label: "", render: (r) => <Chip status={r.tone === "bad" ? "missing" : "pending"}>{r.tone === "bad" ? "Missing" : "Soon"}</Chip> },
        { key: "category", label: "Area", type: "label", filter: true }, { key: "who", label: "Who" }, { key: "what", label: "What" },
      ]} empty="Nothing missing. Every company has an MSA and every consultant has their agreements and policies." />}
      {modal === "agreement" && <AgreementModal onClose={() => setModal(null)} onDone={(a) => router.push(`/contracts/agreements/${a.id}`)} />}
      {modal === "sow" && <SowModal onClose={() => setModal(null)} onDone={(s) => router.push(`/contracts/sows/${s.id}`)} />}
    </>
  );
}

function AgreementModal({ onClose, onDone }: { onClose: () => void; onDone: (a: any) => void }) {
  const consultants = useApi<any[]>("/consultants");
  const [kind, setKind] = useState("msa");
  const [existing, setExisting] = useState(false);
  const { run, busy } = useAction();
  // NDAs are signed with companies (Verify → NDA → MSA) or with consultants.
  const [ndaWith, setNdaWith] = useState<"company" | "consultant">("company");
  const personal = ["offer_letter", "ica"].includes(kind) || (kind === "nda" && ndaWith === "consultant");
  const consultantName = (c: any) => (c.user_code ? c.full_name + " · " + c.user_code : c.full_name);
  return (
    <Modal title="Add agreement" onClose={onClose}>
      <div className="seg" style={{ marginBottom: 8 }}>
        <button className={!existing ? "on" : ""} onClick={() => setExisting(false)}>New draft (send for signature)</button>
        <button className={existing ? "on" : ""} onClick={() => setExisting(true)}>Already signed (record it)</button>
      </div>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        const v: any = formValues(e.currentTarget);
        v.kind = kind; v.status = existing ? "active" : "draft"; v.source = existing ? "manual" : "myTrakIn";
        const r = await run(() => api("/agreements", { body: v }), "Agreement saved");
        if (r) onDone(r);
      }}>
        <div className="fields">
          <Field label="Type" name="kind_select" as="select" value={kind} onChange={(e: any) => setKind(e.target.value)}
                 options={[["msa", "MSA (client or prime)"], ["subcontract", "Subcontractor agreement (vendor)"], ["ica", "Independent contractor agreement (1099)"], ["nda", "NDA"], ["offer_letter", "Offer letter"]]} />
          {kind === "nda" && (
            <Field label="NDA with" name="nda_with" as="select" value={ndaWith} onChange={(e: any) => setNdaWith(e.target.value)}
                   options={[["company", "A client or vendor company"], ["consultant", "A consultant"]]} />
          )}
        {personal ? (
          <Field label="Consultant" name="consultant_id" as="select" required options={[["", "Choose…"], ...(consultants.data ?? []).map((c) => [c.id, consultantName(c)] as [string, string])]} />
        ) : (
          <CompanyPicker label="Company" name="company_id" required />
        )}
          <Field label="You are the" name="tenant_side" as="select" options={personal ? [["employer", "Employer / buyer"], ["buyer", "Buyer"]] : [["supplier", "Supplier (you bill them)"], ["buyer", "Buyer (you pay them)"]]} />
          <Field label="Effective" name="effective_on" type="date" required />
          <Field label="Expires" name="expires_on" type="date" />
          <Field label="Payment terms" name="payment_terms" as="select" options={AGREEMENT_TERMS.payment_terms} />
          <Field label="Renewal" name="renewal" as="select" options={AGREEMENT_TERMS.renewal} />
          <Field label="Notice period" name="notice_period" as="select" options={AGREEMENT_TERMS.notice_period} />
          <Field label="Insurance required" name="insurance_required" as="select" options={AGREEMENT_TERMS.insurance_required} />
          {existing && <Field label="Signed by" name="signed_by" full />}
        </div>
        <p className="note">The agreement number is assigned automatically. {existing ? "After saving, attach the signed PDF on the agreement page." : "After saving, send it for e-signature from the agreement page."}</p>
        <button className="btn pri mt" disabled={busy}>Save agreement</button>
      </form>
    </Modal>
  );
}

function SowModal({ onClose, onDone }: { onClose: () => void; onDone: (s: any) => void }) {
  const agreements = useApi<any[]>("/agreements");
  const sows = useApi<any[]>("/sows", { side: "we_bill" });
  const projects = useApi<any[]>("/projects");
  const [existing, setExisting] = useState(false);
  const [sendNow, setSendNow] = useState(true);
  const [saving, setSaving] = useState(false);
  const { run, busy } = useAction();
  // An MSA either side recorded with one of our companies: work under it runs from here too.
  const pickable = (agreements.data ?? []).filter((a: any) =>
    ["msa", "subcontract", "ica"].includes(a.kind) && a.status !== "rejected" && a.status !== "expired"
      && a.status !== "terminated");
  return (
    <Modal title="Add SOW / work order" onClose={onClose}>
      <div className="seg" style={{ marginBottom: 8 }}>
        <button className={!existing ? "on" : ""} onClick={() => setExisting(false)}>New draft (needs approval)</button>
        <button className={existing ? "on" : ""} onClick={() => setExisting(true)}>Already signed (record it)</button>
      </div>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        setSaving(true);
        const v: any = formValues(e.currentTarget);
        v.status = existing ? "active" : "draft";
        for (const k of ["value_cap", "prior_invoiced", "prior_paid"]) if (v[k]) v[k] = Number(v[k]);
        const r = await run(() => api("/sows", { body: v }), existing ? "SOW saved" : "SOW drafted");
        if (r) {
          // An MSA the other workspace recorded: offer to put it in front of them at once.
          if (!existing && sendNow) {
            await run(() => api(`/sows/${r.id}/submit`, { method: "POST" }),
              "Sent to the other company for approval");
          }
          onDone(r);
        }
        setSaving(false);
      }}>
        <div className="fields">
          <Field label="SOW / work order ID" name="code" placeholder="Leave blank to number it automatically" />
          <Field label="Project" name="project_id" as="select" options={[["", "–"], ...(projects.data ?? []).map((p) => [p.id, `${p.code} · ${p.name}`] as [string, string])]} />
          <Field label="Under agreement" name="agreement_id" as="select" required
            options={[["", "Choose…"], ...pickable.map((a: any) => [a.id, `${a.code} · ${a.counterparty}${a.shared ? " (their MSA)" : ""}`] as [string, string])]} />
          <Field label="Side" name="side" as="select" options={[["we_bill", "We bill (client SOW)"], ["we_pay", "We pay (vendor / 1099 work order)"]]} />
          <Field label="Title" name="title" required />
          <Field label="Start" name="start_date" type="date" required />
          <Field label="End" name="end_date" type="date" required />
          <Field label="Value ceiling ($)" name="value_cap" type="number" step="0.01" min="0" />
          <Field label="Supports client SOW (vendor SOWs)" name="flows_from_sow_id" as="select" options={[["", "–"], ...(sows.data ?? []).map((s: any) => [s.id, `${s.code}${s.project ? ` · ${s.project}` : ""}${s.project_name ? ` – ${s.project_name}` : ""}`] as [string, string])]} />
          <Field label="Invoiced before myTrakIn ($)" name="prior_invoiced" type="number" step="0.01" min="0" />
          <Field label="Collected / paid before myTrakIn ($)" name="prior_paid" type="number" step="0.01" min="0" />
        </div>
        {!existing && (
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <input type="checkbox" checked={sendNow} onChange={(e) => setSendNow(e.target.checked)} style={{ marginTop: 4 }} />
            <span>Send it to the other company for approval straight away
              <span className="muted"> — until you do, it is a draft and they cannot see it</span></span>
          </label>
        )}
        <button className="btn pri mt" disabled={busy || saving}>
          {existing ? "Save SOW" : sendNow ? "Save & send for approval" : "Save draft"}
        </button>
      </form>
    </Modal>
  );
}
