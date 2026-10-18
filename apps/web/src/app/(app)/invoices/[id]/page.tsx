"use client";

import { useParams, useRouter } from "next/navigation";
import { Attachments } from "@/components/Attachments";
import { Chip, ErrorBox, Field, formValues, Loading, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, dateTime, money, num } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";
import { iso } from "@/lib/weeks";

export default function InvoiceDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { workspace } = useSession();
  const { data: inv, error, loading, reload } = useApi(`/invoices/${id}`);
  const { run, busy } = useAction();
  const finance = allows(workspace, "finance");

  if (loading) return <Loading rows={8} />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  const ar = inv.direction === "ar";

  return (
    <>
      <PageHead title={`${ar ? "Client" : "Vendor"} invoice ${inv.number}`} sub={<>{inv.party} · <Chip status={inv.live_status} /></>}
        actions={<>
          <button className="btn" onClick={() => router.back()}>Back</button>
          {finance && ar && inv.status === "draft" && <button className="btn pri" disabled={busy} onClick={async () => { await run(() => api(`/invoices/${id}/send`, { method: "POST" }), "Invoice sent"); reload(); }}>Send to customer</button>}
          {finance && inv.live_status === "exception" && <button className="btn pri" disabled={busy} onClick={async () => { await run(() => api(`/invoices/${id}/resolve`, { method: "POST" }), "Accepted at approved hours"); reload(); }}>Accept at approved hours</button>}
        </>} />

      <div className="grid c2">
        <div className="card">
          <dl className="dl">
            <dt>{ar ? "Customer" : "Payee"}</dt><dd>{inv.party}</dd>
            <dt>Consultant</dt><dd>{inv.consultant ?? "–"}</dd>
            <dt>Project</dt><dd>{inv.project ?? "–"}</dd>
            <dt>SOW</dt><dd>{inv.sow ?? "–"}</dd>
            <dt>Period</dt><dd>{date(inv.period_start)} – {date(inv.period_end)}</dd>
            <dt>Hours × rate</dt><dd>{num(inv.hours, 2)} × {money(inv.rate)}</dd>
            <dt>Amount</dt><dd><b>{money(inv.amount)}</b></dd>
            <dt>Paid</dt><dd>{money(inv.paid)}</dd>
            {Number(inv.credited) > 0 && <><dt>Credited</dt><dd>{money(inv.credited)}</dd></>}
            <dt>Balance</dt><dd><b>{money(inv.balance)}</b></dd>
            <dt>Issued / due</dt><dd>{date(inv.issued_on)} · {inv.due_on ? `due ${date(inv.due_on)}` : "pay-when-paid"}{inv.days_late > 0 && <span className="err"> · {inv.days_late} days late</span>}</dd>
            <dt>Terms</dt><dd>{inv.terms ?? "–"}</dd>
            {inv.po_number && <><dt>PO</dt><dd>{inv.po_number}</dd></>}
          </dl>
          {inv.match && (
            <>
              <h3>Three-way match</h3>
              <div className="match">
                <div><b>{num(inv.match.invoiced_hours, 2)}</b>Invoiced hours</div>
                <div><b>{num(inv.match.approved_hours, 2)}</b>Approved timesheets</div>
                <div><b>{inv.match.billed_to_customer_hours == null ? "••" : num(inv.match.billed_to_customer_hours, 2)}</b>Billed to customer</div>
              </div>
              <p className={inv.match.matches ? "ok" : "err"}>{inv.match.matches ? "Hours match the approved timesheets." : "Hours don't match — accept at approved hours or ask the vendor to re-issue."}</p>
              {inv.waits_for && <p className="note">Pay-when-paid: waits for client invoice {inv.waits_for.number} ({inv.waits_for.live_status.replace(/_/g, " ")}).</p>}
            </>
          )}
        </div>

        <div className="card">
          <h3>Payments</h3>
          {inv.payments.length ? (
            <table><tbody>{inv.payments.map((p: any) => (
              <tr key={p.id}>
                <td>{date(p.paid_on)}</td><td>{p.method}</td><td>{p.reference}</td><td className="num">{money(p.amount)}</td>
                <td><Chip status={p.status === "confirmed" ? "ok" : p.status === "completed" ? "paid" : "pending"}>{p.status}</Chip>
                  {p.confirmed_by_name && <div className="muted" style={{ fontSize: 12 }}>by {p.confirmed_by_name}, {date(p.confirmed_at)}</div>}</td>
                <td>
                  {finance && ["pending", "processing"].includes(p.status) && (
                    <button className="btn sm" disabled={busy} onClick={async () => {
                      const next = p.status === "pending" ? "processing" : "completed";
                      if (await run(() => api(`/payments/${p.id}/status`, { body: { status: next } }), `Marked ${next}`)) reload();
                    }}>{p.status === "pending" ? "Mark processing" : "Mark completed"}</button>
                  )}
                  {p.status === "completed" && (finance || !ar) && (
                    <button className="btn sm" disabled={busy} onClick={async () => {
                      if (await run(() => api(`/payments/${p.id}/confirm`, { method: "POST" }), "Payment confirmed")) reload();
                    }}>{ar ? "Confirm received" : "Confirm payment"}</button>
                  )}
                </td>
              </tr>
            ))}</tbody></table>
          ) : <p className="muted">No payments yet.</p>}
          {finance && Number(inv.balance) > 0 && inv.status !== "void" && (
            <form className="form mt" onSubmit={async (e) => {
              e.preventDefault();
              const v = formValues(e.currentTarget);
              if (await run(() => api(`/invoices/${id}/payments`, { body: { ...v, amount: Number(v.amount) } }), "Payment recorded")) reload();
            }}>
              <div className="fields">
                <Field label="Amount" name="amount" type="number" step="0.01" min="0.01" defaultValue={inv.balance} required />
                <Field label="Date" name="paid_on" type="date" defaultValue={iso(new Date())} required />
                <Field label="Method" name="method" as="select" options={["ACH", "Wire", "Check", "Card", "Other"]} />
                <Field label="Reference" name="reference" placeholder="Trace / check number" />
                <Field label="Status" name="status" as="select" options={[["completed", "Completed (money moved)"], ["processing", "Processing"], ["pending", "Pending"]]} />
              </div>
              <p className="note">Pending and processing payments don't reduce the balance until marked completed. Confirmation by the receiving side closes the payment.</p>
              <button className="btn pri mt" disabled={busy}>{ar ? "Record payment received" : "Record payment made"}</button>
            </form>
          )}

          {ar && (inv.credits?.length > 0 || (finance && inv.status !== "draft" && inv.status !== "void" && Number(inv.balance) > 0)) && (
            <>
              <h3 className="mt">Credit notes</h3>
              {inv.credits?.length > 0 && (
                <table><tbody>{inv.credits.map((c: any) => (
                  <tr key={c.id}><td>{c.number}</td><td>{date(c.issued_on)}</td><td>{c.reason}</td><td className="num">−{money(c.amount)}</td></tr>
                ))}</tbody></table>
              )}
              {finance && inv.status !== "draft" && inv.status !== "void" && Number(inv.balance) > 0 && (
                <form className="form mt" onSubmit={async (e) => {
                  e.preventDefault();
                  const v = formValues(e.currentTarget);
                  if (await run(() => api(`/invoices/${id}/credit-notes`, { body: { ...v, amount: Number(v.amount) } }), "Credit note issued")) reload();
                }}>
                  <div className="fields">
                    <Field label="Credit amount" name="amount" type="number" step="0.01" min="0.01" max={inv.balance} required />
                    <Field label="Reason" name="reason" placeholder="8 holiday hours billed at the regular rate" required minLength={3} full />
                  </div>
                  <p className="note">Lowers what the customer owes on this invoice. A fully credited invoice counts as settled and releases pay-when-paid vendor invoices.</p>
                  <button className="btn mt" disabled={busy}>Issue credit note</button>
                </form>
              )}
            </>
          )}

          {inv.notes && (
            <>
              <h3 className="mt">Follow-up notes</h3>
              <div className="timeline">
                {inv.notes.map((n: any, i: number) => <div key={i} className="ev">{n.body}<small>{n.author_name} · {dateTime(n.created_at)}</small></div>)}
              </div>
              <form className="row" onSubmit={async (e) => {
                e.preventDefault();
                const form = e.currentTarget;
                if (await run(() => api(`/invoices/${id}/notes`, { body: formValues(form) }), "Note added")) { form.reset(); reload(); }
              }}>
                <input name="body" className="ctl" style={{ flex: 1 }} placeholder="Called AP — payment run on Friday" required minLength={2} />
                <button className="btn" disabled={busy}>Add note</button>
              </form>
            </>
          )}
          {finance && inv.status !== "void" && Number(inv.paid) === 0 && !inv.credits?.length && (
            <p className="note mt"><a onClick={async () => {
              const reason = prompt("Why is this invoice being voided?");
              if (reason && await run(() => api(`/invoices/${id}/void`, { body: { body: reason } }), "Invoice voided")) reload();
            }}>Void this invoice</a></p>
          )}
        </div>
      </div>
      <Attachments ownerType="invoice" ownerId={id} canEdit={finance} />
    </>
  );
}
