"use client";

import { useState } from "react";
import { DataButtons } from "@/components/DataButtons";
import { DataTable } from "@/components/DataTable";
import { Chip, ErrorBox, Field, formValues, Modal, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, label, money } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

type Tab = "payroll" | "1099" | "referrals" | "expenses" | "time_off";

/** People paid outside the vendor chain: W-2 payroll, referral fees, the 1099 summary, expenses and time off. */
export default function PeoplePay() {
  const { workspace } = useSession();
  const finance = allows(workspace, "finance");
  const tabs: [Tab, string, boolean][] = [
    ["payroll", "W-2 payroll", finance], ["1099", "1099 summary", finance], ["referrals", "Referral fees", allows(workspace, "finance", "hr")],
    ["expenses", "Expenses", allows(workspace, "finance", "hr", "approver")], ["time_off", "Time off", allows(workspace, "hr", "approver", "account_manager")],
  ];
  const visible = tabs.filter(([, , ok]) => ok);
  const [tab, setTab] = useState<Tab>(visible[0]?.[0] ?? "expenses");
  return (
    <>
      <PageHead title="Payroll, 1099 & referrals" sub="W-2 salaries, referral fees and contractor payments for year-end 1099s, plus expense and time-off approvals." />
      <div className="tabs">{visible.map(([k, t]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{t}</button>)}</div>
      {tab === "payroll" && <Payroll />}
      {tab === "1099" && <Form1099 />}
      {tab === "referrals" && <Referrals />}
      {tab === "expenses" && <Expenses />}
      {tab === "time_off" && <TimeOff />}
    </>
  );
}

function Payroll() {
  const { data, error, reload } = useApi<any[]>("/payroll");
  const consultants = useApi<any[]>("/consultants");
  const [adding, setAdding] = useState(false);
  const { run, busy } = useAction();
  return (
    <>
      <p className="muted" style={{ marginTop: 0 }}>Run payroll in your payroll provider, then import or enter the results here so margins and cash flow are complete.</p>
      <ErrorBox error={error} retry={reload} />
      <DataTable id="payroll" rows={data} columns={[
        { key: "pay_date", label: "Pay date", type: "date" }, { key: "full_name", label: "Employee", filter: true },
        { key: "period", label: "Period", value: (r) => `${date(r.period_start)} – ${date(r.period_end)}` },
        { key: "hours", label: "Hours", type: "number" }, { key: "gross", label: "Gross", type: "money" },
        { key: "employer_taxes", label: "Employer taxes", type: "money", hideSm: true }, { key: "benefits", label: "Benefits", type: "money", hideSm: true },
        { key: "total_cost", label: "Total cost", type: "money" }, { key: "source", label: "Source", filter: true, hideSm: true },
      ]} toolbar={<><button className="btn sm pri" onClick={() => setAdding(true)}>Add pay run line</button><DataButtons entity="payroll" label="payroll" /></>} />
      {adding && (
        <Modal title="Add a payroll line" onClose={() => setAdding(false)}>
          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            const v: any = formValues(e.currentTarget);
            for (const k of ["hours", "gross", "employer_taxes", "benefits", "net"]) if (v[k]) v[k] = Number(v[k]);
            if (await run(() => api("/payroll", { body: v }), "Saved")) { setAdding(false); reload(); }
          }}>
            <div className="fields">
              <Field label="W-2 employee" name="consultant_id" as="select" required full
                     options={[["", "Choose…"], ...(consultants.data ?? []).filter((c) => c.engagement.startsWith("w2")).map((c) => [c.id, c.full_name] as [string, string])]} />
              <Field label="Period start" name="period_start" type="date" required />
              <Field label="Period end" name="period_end" type="date" required />
              <Field label="Pay date" name="pay_date" type="date" required />
              <Field label="Hours" name="hours" type="number" step="0.01" />
              <Field label="Gross pay" name="gross" type="number" step="0.01" required />
              <Field label="Employer taxes" name="employer_taxes" type="number" step="0.01" />
              <Field label="Benefits" name="benefits" type="number" step="0.01" />
              <Field label="Net pay" name="net" type="number" step="0.01" />
            </div>
            <button className="btn pri mt" disabled={busy}>Save</button>
          </form>
        </Modal>
      )}
    </>
  );
}

function Form1099() {
  const [year, setYear] = useState(new Date().getFullYear());
  const { data, error, reload } = useApi("/form-1099", { year });
  return (
    <>
      <div className="toolbar">
        <label htmlFor="yr" style={{ margin: 0 }}>Tax year</label>
        <select id="yr" className="ctl" value={year} onChange={(e) => setYear(Number(e.target.value))}>
          {[0, 1, 2, 3].map((d) => new Date().getFullYear() - d).map((y) => <option key={y}>{y}</option>)}
        </select>
        {data && <span className="muted">Reporting threshold {money(data.threshold, true)}</span>}
      </div>
      <ErrorBox error={error} retry={reload} />
      <DataTable<any> id="form-1099" rows={data?.rows} columns={[
        { key: "payee", label: "Payee" }, { key: "kind", label: "Paid as", type: "label", filter: true },
        { key: "paid", label: "Paid in year", type: "money" }, { key: "invoices", label: "Payments", type: "number" },
        { key: "w9_on_file", label: "W-9", render: (r) => <Chip status={r.w9_on_file ? "ok" : "missing"}>{r.w9_on_file ? "On file" : "Missing"}</Chip>, value: (r) => (r.w9_on_file ? "On file" : "Missing") },
        { key: "reportable", label: "1099-NEC", render: (r) => (r.reportable ? <Chip status="pending">File</Chip> : <span className="muted">Below threshold</span>), value: (r) => (r.reportable ? "File" : "Below") },
      ]} empty="No payments to 1099 contractors or individual referrers this year." />
      {data && <p className="note">{data.note}</p>}
    </>
  );
}

function Referrals() {
  const { workspace } = useSession();
  const { data, error, reload } = useApi<any[]>("/referrals");
  const consultants = useApi<any[]>("/consultants");
  const [adding, setAdding] = useState(false);
  const [basis, setBasis] = useState("hourly");
  const { run, busy } = useAction();
  return (
    <>
      <ErrorBox error={error} retry={reload} />
      <DataTable id="referrals" rows={data} columns={[
        { key: "referrer_name", label: "Referrer" }, { key: "referrer_type", label: "Type", type: "label", filter: true },
        { key: "consultant", label: "Referred consultant" },
        { key: "terms", label: "Terms", value: (r) => (r.basis === "hourly" ? `$${r.rate_per_hour}/h${r.hour_cap ? ` up to ${Number(r.hour_cap)} h` : ""}` : `One-time ${money(r.one_time_amount, true)}${r.eligible_on ? ` after ${date(r.eligible_on)}` : ""}`) },
        { key: "earned", label: "Earned", type: "money" }, { key: "paid", label: "Paid", type: "money" }, { key: "balance", label: "Due", type: "money" },
        { key: "w9", label: "W-9", value: (r) => (r.referrer_type !== "individual_1099" ? "n/a" : r.w9_on_file ? "On file" : "Missing"),
          render: (r) => r.referrer_type !== "individual_1099" ? <span className="muted">n/a</span> : (
            <button className="btn sm" onClick={async () => { await run(() => api(`/referrals/${r.id}`, { method: "PATCH", query: { w9_on_file: !r.w9_on_file } }), "Updated"); reload(); }}>
              {r.w9_on_file ? "On file ✓" : "Mark received"}</button>) },
        { key: "pay", label: "", render: (r) => allows(workspace, "finance") && Number(r.balance) > 0 ? (
            <button className="btn sm pri" disabled={busy} onClick={async () => {
              const amount = prompt(`Amount to pay ${r.referrer_name} (up to $${r.balance}):`, String(r.balance));
              if (amount && await run(() => api(`/referrals/${r.id}/payments`, { body: { amount: Number(amount), paid_on: new Date().toISOString().slice(0, 10) } }), "Payment recorded")) reload();
            }}>Pay</button>) : null },
      ]} toolbar={<button className="btn sm pri" onClick={() => setAdding(true)}>New referral agreement</button>} />
      <p className="note">Hourly fees count approved timesheet hours from the eligibility date. Individuals paid as 1099 need a W-9 before the first payment.</p>
      {adding && (
        <Modal title="New referral agreement" onClose={() => setAdding(false)}>
          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            const v: any = formValues(e.currentTarget);
            v.basis = basis;
            for (const k of ["rate_per_hour", "hour_cap", "one_time_amount"]) if (v[k]) v[k] = Number(v[k]);
            v.w9_on_file = v.w9_on_file === "yes";
            if (await run(() => api("/referrals", { body: v }), "Referral agreement saved")) { setAdding(false); reload(); }
          }}>
            <div className="fields">
              <Field label="Referrer" name="referrer_name" required />
              <Field label="Referrer is" name="referrer_type" as="select" options={[["individual_1099", "Individual (1099)"], ["company", "Company"], ["employee", "Our employee (pay via payroll)"]]} />
              <Field label="Referred consultant" name="consultant_id" as="select" required full options={[["", "Choose…"], ...(consultants.data ?? []).map((c) => [c.id, c.full_name] as [string, string])]} />
              <Field label="Basis" name="basis_pick" as="select" value={basis} onChange={(e: any) => setBasis(e.target.value)} options={[["hourly", "Per hour worked"], ["one_time", "One-time fee"]]} />
              {basis === "hourly" ? <>
                <Field label="Rate per hour ($)" name="rate_per_hour" type="number" step="0.01" required />
                <Field label="Up to (hours)" name="hour_cap" type="number" />
              </> : <Field label="Amount ($)" name="one_time_amount" type="number" step="0.01" required />}
              <Field label="Eligible from" name="eligible_on" type="date" />
              <Field label="W-9 on file" name="w9_on_file" as="select" options={[["no", "No"], ["yes", "Yes"]]} />
            </div>
            <button className="btn pri mt" disabled={busy}>Save</button>
          </form>
        </Modal>
      )}
    </>
  );
}

function Expenses() {
  const { workspace } = useSession();
  const { data, error, reload } = useApi<any[]>("/expenses");
  const { run, busy } = useAction();
  const decide = async (id: string, decision: string) => { if (await run(() => api(`/expenses/${id}/decision`, { body: { decision } }), label(decision))) reload(); };
  return (
    <>
      <ErrorBox error={error} retry={reload} />
      <DataTable id="expenses" rows={data} columns={[
        { key: "spent_on", label: "Date", type: "date" }, { key: "consultant", label: "Consultant", filter: true }, { key: "project", label: "Project", hideSm: true },
        { key: "category", label: "Category" }, { key: "amount", label: "Amount", type: "money" },
        { key: "billable", label: "Billable", value: (r) => (r.billable ? "Yes" : "No"), filter: true }, { key: "status", label: "Status", type: "status", filter: true },
        { key: "act", label: "", render: (r) => r.status === "submitted" ? <span className="row">
            <button className="btn sm pri" disabled={busy} onClick={() => decide(r.id, "approved")}>Approve</button>
            <button className="btn sm" disabled={busy} onClick={() => decide(r.id, "rejected")}>Reject</button></span>
          : r.status === "approved" && allows(workspace, "finance") ? <button className="btn sm" disabled={busy} onClick={() => decide(r.id, "reimbursed")}>Mark reimbursed</button> : null },
      ]} empty="No expenses submitted." />
    </>
  );
}

function TimeOff() {
  const { data, error, reload } = useApi<any[]>("/time-off");
  const { run, busy } = useAction();
  const decide = async (id: string, decision: string) => { if (await run(() => api(`/time-off/${id}/decision`, { body: { decision } }), label(decision))) reload(); };
  return (
    <>
      <ErrorBox error={error} retry={reload} />
      <DataTable id="time-off" rows={data} columns={[
        { key: "consultant", label: "Consultant", filter: true }, { key: "kind", label: "Type", type: "label", filter: true },
        { key: "starts_on", label: "From", type: "date" }, { key: "ends_on", label: "To", type: "date" }, { key: "days", label: "Days", type: "number" },
        { key: "note", label: "Note", hideSm: true }, { key: "status", label: "Status", type: "status", filter: true },
        { key: "act", label: "", render: (r) => r.status === "requested" ? <span className="row">
            <button className="btn sm pri" disabled={busy} onClick={() => decide(r.id, "approved")}>Approve</button>
            <button className="btn sm" disabled={busy} onClick={() => decide(r.id, "declined")}>Decline</button></span> : null },
      ]} empty="No time-off requests." />
    </>
  );
}
