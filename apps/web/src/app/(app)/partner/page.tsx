"use client";

import { useEffect, useState } from "react";
import { DataTable } from "@/components/DataTable";
import { Field, formValues, Modal, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

/** Home for vendors (their consultants, timesheets, invoices to us) and clients (our invoices to them). */
export default function PartnerHome() {
  const { workspace } = useSession();
  const vendor = workspace?.role === "vendor_admin";
  const invoices = useApi<any[]>("/invoices", { direction: vendor ? "ap" : "ar" });
  const placements = useApi<any[]>("/placements");
  const consultants = useApi<any[]>(vendor ? "/consultants" : null);
  const history = useApi<any[]>(vendor ? "/timesheets/history" : null);
  const [submitting, setSubmitting] = useState(false);
  const { run, busy } = useAction();

  // Balances and statuses change when finance records a payment or a new invoice
  // arrives: refresh this page while it is open and when the tab is focused again.
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState !== "visible") return;
      invoices.reload();
      placements.reload();
      if (vendor) {
        consultants.reload();
        history.reload();
      }
    };
    const timer = setInterval(refresh, 60_000);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [vendor, invoices.reload, placements.reload, consultants.reload, history.reload]);

  return (
    <>
      <PageHead title={workspace?.tenant.name ?? ""} sub={vendor ? "Your consultants, their approved hours, and the invoices you send us." : "Invoices we've sent you and the people working on your projects."}
        actions={vendor && <button className="btn pri" onClick={() => setSubmitting(true)}>Submit an invoice</button>} />
      <h2>{vendor ? "Your invoices to us" : "Our invoices to you"}</h2>
      <DataTable id="partner-invoices" rows={invoices.data} columns={[
        { key: "number", label: "Invoice" }, { key: "consultant", label: "Consultant", filter: true }, { key: "period_start", label: "Period", type: "date" },
        { key: "hours", label: "Hours", type: "number" }, { key: "approved_hours", label: "Approved hours", type: "number", hideSm: true },
        { key: "amount", label: "Amount", type: "money" }, { key: "balance", label: "Balance", type: "money" },
        { key: "due_on", label: "Due", type: "date" }, { key: "live_status", label: "Status", type: "status", filter: true },
      ]} empty="No invoices yet." />
      {vendor && <p className="note">Pay-when-paid invoices show “held” until our client pays us, then move to ready to pay. Invoices that don't match approved hours show “exception”.</p>}
      <h2 className="mt">Placements</h2>
      <DataTable id="partner-placements" rows={placements.data} columns={[
        { key: "consultant", label: "Consultant" }, { key: "project", label: "Project" }, { key: "role_title", label: "Role", hideSm: true },
        { key: "start_date", label: "Start", type: "date" }, { key: "end_date", label: "End", type: "date" },
        vendor ? { key: "pay_rate", label: "Rate we pay", type: "money" } : { key: "bill_rate", label: "Rate", type: "money" },
        { key: "status", label: "Status", type: "status" },
      ]} />
      {vendor && <>
        <h2 className="mt">Timesheets of your consultants</h2>
        <DataTable id="partner-timesheets" rows={history.data} columns={[
          { key: "week_start", label: "Week", type: "date" }, { key: "full_name", label: "Consultant", filter: true },
          { key: "project", label: "Project" }, { key: "hours", label: "Hours", type: "number" }, { key: "status", label: "Status", type: "status", filter: true },
        ]} />
        <p className="note">{consultants.data?.length ?? 0} of your consultants work with us. Invoice only approved hours.</p>
      </>}
      {submitting && (
        <Modal title="Submit an invoice" onClose={() => setSubmitting(false)}>
          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            const v: any = formValues(e.currentTarget);
            v.hours = Number(v.hours);
            const r = await run(() => api("/vendor-invoices", { body: v }));
            if (r) { alert(r.status === "received" ? `Invoice ${r.number} received — hours match.` : `Invoice ${r.number} received, but the hours don't match approved timesheets. Our AP team will contact you.`); setSubmitting(false); invoices.reload(); }
          }}>
            <div className="fields">
              <Field label="Your invoice number" name="number" required />
              <Field label="Placement" name="placement_id" as="select" required options={[["", "Choose…"], ...(placements.data ?? []).map((p) => [p.id, `${p.consultant} · ${p.project}`] as [string, string])]} />
              <Field label="Period start" name="period_start" type="date" required />
              <Field label="Period end" name="period_end" type="date" required />
              <Field label="Hours" name="hours" type="number" step="0.25" min="0.25" required />
            </div>
            <p className="note">The amount is calculated from the agreed rate. Attach your PDF after submitting, from the invoice.</p>
            <button className="btn pri mt" disabled={busy}>Submit</button>
          </form>
        </Modal>
      )}
    </>
  );
}
