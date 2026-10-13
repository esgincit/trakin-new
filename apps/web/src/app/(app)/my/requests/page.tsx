"use client";

import { Chip, Field, formValues, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, label, money } from "@/lib/format";
import { useApi } from "@/lib/useApi";

/** Consultants submit expenses and ask for time off; approvers decide under Payroll, 1099 & referrals. */
export default function MyRequests() {
  const expenses = useApi<any[]>("/me/expenses");
  const timeOff = useApi<any[]>("/me/time-off");
  const overview = useApi("/me/consultant");
  const { run, busy } = useAction();
  const today = new Date().toISOString().slice(0, 10);

  return (
    <>
      <PageHead title="Expenses & time off" sub="Submit expenses for reimbursement and request time off. You'll see the decision here." />
      <div className="grid c2">
        <form className="card form" onSubmit={async (e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const v: any = formValues(form);
          v.amount = Number(v.amount);
          v.billable = v.billable === "yes";
          if (await run(() => api("/me/expenses", { body: v }), "Expense submitted")) { form.reset(); expenses.reload(); }
        }}>
          <h3>New expense</h3>
          <div className="fields">
            <Field label="Date" name="spent_on" type="date" max={today} required />
            <Field label="Amount ($)" name="amount" type="number" step="0.01" min="0.01" required />
            <Field label="Category" name="category" required placeholder="Travel, meals, certification…" full />
            <Field label="Project" name="placement_id" as="select" options={[["", "Not project-related"], ...(overview.data?.projects ?? []).map((p: any) => [p.placement_id, p.project] as [string, string])]} />
            <Field label="Billable to client" name="billable" as="select" options={[["yes", "Yes"], ["no", "No"]]} />
          </div>
          <p className="note">Keep the receipt — your approver may ask for it.</p>
          <button className="btn pri mt" disabled={busy}>Submit expense</button>
        </form>
        <form className="card form" onSubmit={async (e) => {
          e.preventDefault();
          const form = e.currentTarget;
          if (await run(() => api("/me/time-off", { body: formValues(form) }), "Request sent")) { form.reset(); timeOff.reload(); }
        }}>
          <h3>Request time off</h3>
          <div className="fields">
            <Field label="From" name="starts_on" type="date" required />
            <Field label="To" name="ends_on" type="date" required />
            <Field label="Type" name="kind" as="select" options={[["pto", "Paid time off"], ["sick", "Sick"], ["unpaid", "Unpaid"]]} full />
            <Field label="Note" name="note" full />
          </div>
          <button className="btn pri mt" disabled={busy}>Send request</button>
        </form>
      </div>
      <div className="grid c2 mt">
        <div className="card">
          <h3>My expenses</h3>
          {expenses.data?.map((x) => <div key={x.id} className="alert"><Chip status={x.status} /><div style={{ flex: 1 }}>{x.category}<div className="muted" style={{ fontSize: 12.5 }}>{date(x.spent_on)}</div></div><b>{money(x.amount)}</b></div>)}
          {expenses.data && !expenses.data.length && <p className="muted">None yet.</p>}
        </div>
        <div className="card">
          <h3>My time off</h3>
          {timeOff.data?.map((x) => <div key={x.id} className="alert"><Chip status={x.status} /><div>{label(x.kind)} · {date(x.starts_on)} – {date(x.ends_on)}{x.note && <div className="muted" style={{ fontSize: 12.5 }}>{x.note}</div>}</div></div>)}
          {timeOff.data && !timeOff.data.length && <p className="muted">None yet.</p>}
        </div>
      </div>
    </>
  );
}
