"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { DataTable, type Column } from "@/components/DataTable";
import { ErrorBox, Field, formValues, ImportButton, Modal, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { allows, isStaff, canEdit as permits, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";
import { iso } from "@/lib/weeks";

const columns: Column<any>[] = [
  { key: "number", label: "Invoice" },
  { key: "party", label: "Customer / payee", filter: true },
  { key: "consultant", label: "Consultant", filter: true, hideSm: true },
  { key: "sow", label: "SOW", hideSm: true },
  { key: "period_start", label: "Period", type: "date", hideSm: true },
  { key: "hours", label: "Hours", type: "number", hideSm: true },
  { key: "amount", label: "Amount", type: "money" },
  { key: "balance", label: "Balance", type: "money" },
  { key: "due_on", label: "Due", type: "date" },
  { key: "live_status", label: "Status", type: "status", filter: true },
];

const creditColumns: Column<any>[] = [
  { key: "number", label: "Credit note" },
  { key: "customer", label: "Customer", filter: true },
  { key: "invoice", label: "Against" },
  { key: "issued_on", label: "Date", type: "date" },
  { key: "reason", label: "Reason", hideSm: true },
  { key: "amount", label: "Amount", type: "money" },
  { key: "status", label: "Status", type: "status", filter: true },
];

export default function InvoicesPage() {
  return <Suspense><Invoices /></Suspense>;
}

function Invoices() {
  const params = useSearchParams();
  const router = useRouter();
  const { workspace } = useSession();
  const tab = params.get("tab");
  const [direction, setDirection] = useState<"ar" | "ap" | "credits">(tab === "ap" || tab === "credits" ? tab : "ar");
  const credits = direction === "credits";
  const { data, error, reload } = useApi<any[]>(credits ? "/credit-notes" : "/invoices", credits ? undefined : { direction });
  const [modal, setModal] = useState<"generate" | "run" | "manual" | null>(params.get("generate") ? "generate" : null);
  const finance = allows(workspace, "finance");

  return (
    <>
      <PageHead title="Invoices" sub="AR: what customers owe you. AP: what you owe vendors and 1099 contractors."
        actions={finance && permits(workspace, "invoices") && (
          <>
            <ImportButton entity={direction === "ap" ? "ap_invoices" : "ar_invoices"} />
            <button className="btn" onClick={() => setModal("manual")}>New client invoice</button>
            <button className="btn" onClick={() => setModal("run")}>Payment run</button>
            <button className="btn pri" onClick={() => setModal("generate")}>Create invoices from timesheets</button>
          </>
        )} />
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={direction === "ar"} className={direction === "ar" ? "on" : ""} onClick={() => setDirection("ar")}>Client invoices (AR)</button>
        <button role="tab" aria-selected={direction === "ap"} className={direction === "ap" ? "on" : ""} onClick={() => setDirection("ap")}>Vendor & 1099 invoices (AP)</button>
        {isStaff(workspace?.role) && <button role="tab" aria-selected={credits} className={credits ? "on" : ""} onClick={() => setDirection("credits")}>Credit notes</button>}
      </div>
      <ErrorBox error={error} retry={reload} />
      {credits ? (
        <DataTable id="invoices-credits" rows={data} columns={creditColumns} onRowClick={(r) => router.push(`/invoices/${r.invoice_id}`)}
                   empty="No credit notes. Issue one from a client invoice when the customer was over-billed." />
      ) : (
        <><DataTable id={`invoices-${direction}`} rows={data} columns={columns}
                     onRowClick={(r) => router.push(`/invoices/${r.id}`)}
                     empty={direction === "ar" ? "No client invoices yet. Approve timesheets, then create invoices from them." : "No vendor invoices yet."} />
          {direction === "ap" && (data ?? []).some((r: any) => r.is_client_payable) && (
            <p className="note">Note: rows whose party is another workspace are invoices that company sent us — open one to record the payment you made (in full or in part); the provider acknowledges it.</p>
          )}
        </>
      )}
      {modal === "generate" && <GenerateModal onClose={() => setModal(null)} onDone={reload} />}
      {modal === "manual" && <ManualInvoiceModal onClose={() => setModal(null)} onDone={(id) => router.push(`/invoices/${id}`)} />}
      {modal === "run" && <PaymentRunModal rows={direction === "ap" ? data : undefined} onClose={() => setModal(null)} onDone={reload} />}
    </>
  );
}

function GenerateModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { run, busy } = useAction();
  const [result, setResult] = useState<any[] | null>(null);
  const [blocked, setBlocked] = useState<string[]>([]);
  const today = new Date();
  const first = iso(new Date(today.getFullYear(), today.getMonth() - 1, 1));
  const last = iso(new Date(today.getFullYear(), today.getMonth(), 0));
  return (
    <Modal title="Create invoices from approved timesheets" onClose={onClose}>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        const r = await run(() => api("/invoices/generate", { body: formValues(e.currentTarget) }));
        if (r) { setResult(r.created); setBlocked(r.blocked ?? []); onDone(); }
      }}>
        <p className="muted">One client invoice per placement for the approved hours in the period, plus the matching vendor or 1099 payable.
          Hours already invoiced are skipped, so running it twice is safe.</p>
        <div className="fields">
          <Field label="From" name="period_start" type="date" defaultValue={first} required />
          <Field label="To" name="period_end" type="date" defaultValue={last} required />
        </div>
        <button className="btn pri mt" disabled={busy}>Create drafts</button>
      </form>
      {result && <p className="ok">{result.length ? `${result.length} invoice(s) created as drafts. Review and send them from the AR list.` : "Nothing new to invoice for that period."}</p>}
      {blocked.length > 0 && <p className="err">Not invoiced (no active agreement): {blocked.join("; ")}</p>}
    </Modal>
  );
}

function PaymentRunModal({ rows, onClose, onDone }: { rows?: any[]; onClose: () => void; onDone: () => void }) {
  const payable = (rows ?? []).filter((r) => !r.is_client_payable && Number(r.balance) > 0 && ["open", "ready_to_pay", "scheduled", "overdue"].includes(r.live_status));
  const [picked, setPicked] = useState<string[]>(payable.map((r) => r.id));
  const { run, busy } = useAction();
  const total = payable.filter((r) => picked.includes(r.id)).reduce((s, r) => s + Number(r.balance), 0);
  return (
    <Modal title="Payment run" onClose={onClose}>
      {!rows ? <p className="muted">Open the AP tab first to choose vendor invoices.</p> : payable.length === 0 ? <p className="muted">Nothing is ready to pay. Held (pay-when-paid) and mismatched invoices are left out.</p> : (
        <form className="form" onSubmit={async (e) => {
          e.preventDefault();
          const v = formValues(e.currentTarget);
          const r = await run(() => api("/payment-runs", { body: { invoice_ids: picked, method: v.method, paid_on: v.paid_on } }), "Payment run recorded");
          if (r) { onDone(); onClose(); }
        }}>
          {payable.map((r) => (
            <label key={r.id} className="row" style={{ color: "var(--ink)" }}>
              <input type="checkbox" checked={picked.includes(r.id)} onChange={(e) => setPicked((p) => e.target.checked ? [...p, r.id] : p.filter((x) => x !== r.id))} />
              {r.number} · {r.party} · <b>${Number(r.balance).toLocaleString("en-US", { minimumFractionDigits: 2 })}</b>
            </label>
          ))}
          <div className="fields">
            <Field label="Method" name="method" as="select" options={["ACH", "Wire", "Check"]} />
            <Field label="Paid on" name="paid_on" type="date" defaultValue={iso(new Date())} />
          </div>
          <button className="btn pri mt" disabled={busy || !picked.length}>Record {picked.length} payment(s) · ${total.toLocaleString("en-US", { minimumFractionDigits: 2 })}</button>
        </form>
      )}
    </Modal>
  );
}

function ManualInvoiceModal({ onClose, onDone }: { onClose: () => void; onDone: (id: string) => void }) {
  const placements = useApi<any[]>("/placements");
  const { run, busy } = useAction();
  return (
    <Modal title="New client invoice" onClose={onClose}>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        const v: any = formValues(e.currentTarget);
        v.hours = Number(v.hours);
        v.send = v.send === "yes";
        const r = await run(() => api("/invoices", { body: v }), v.send ? "Invoice created and e-mailed" : "Draft created");
        if (r) onDone(r.id);
      }}>
        <div className="fields">
          <Field label="Placement" name="placement_id" as="select" required full
                 options={[["", "Choose…"], ...(placements.data ?? []).filter((p) => p.bill_rate != null).map((p) => [p.id, `${p.consultant} · ${p.project} · ${p.ar_company} @ $${p.bill_rate}`] as [string, string])]} />
          <Field label="Period start" name="period_start" type="date" required />
          <Field label="Period end" name="period_end" type="date" required />
          <Field label="Hours" name="hours" type="number" step="0.25" min="0.25" required />
          <Field label="PO number" name="po_number" />
          <Field label="Memo" name="memo" full />
          <Field label="Send now" name="send" as="select" options={[["yes", "Yes — e-mail the customer"], ["no", "No — save as draft"]]} />
        </div>
        <p className="note">Rate and terms come from the placement. Prefer “Create invoices from timesheets” so hours always match approvals.</p>
        <button className="btn pri mt" disabled={busy}>Create invoice</button>
      </form>
    </Modal>
  );
}
