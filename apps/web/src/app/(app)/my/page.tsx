"use client";

import Link from "next/link";
import { Chip, ErrorBox, Loading, PageHead } from "@/components/ui";
import { date, daysLeft, label } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

/** The consultant's home: projects, the payment chain and where each payment is — never amounts. */
export default function MyWork() {
  const { workspace } = useSession();
  const { data, error, loading, reload } = useApi("/me/consultant");
  if (loading) return <Loading rows={8} />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  const { me, projects, payments, to_sign, policies, documents } = data;
  const openPolicies = policies.filter((p: any) => !p.accepted_at);
  const authDays = me.work_auth_expires ? Math.round((new Date(me.work_auth_expires).getTime() - Date.now()) / 86400000) : null;

  return (
    <>
      <PageHead title={`Hi ${me.full_name.split(" ")[0]}`} sub={`${me.title ?? ""} · ${label(me.engagement)}${me.employer ? ` through ${me.employer}` : ""}`}
        actions={<Link className="btn pri" href="/my/timesheet">Enter this week's hours</Link>} />

      {(to_sign.length > 0 || openPolicies.length > 0) && (
        <div className="card" style={{ borderColor: "var(--warn)", marginBottom: 16 }}>
          <h3>To do</h3>
          {to_sign.map((e: any) => <div key={e.id} className="alert"><Chip status="out_for_signature">Sign</Chip>{e.title} — check your e-mail for the signing link.</div>)}
          {openPolicies.map((p: any) => <div key={p.id} className="alert"><Chip status="pending">Policy</Chip><Link href="/my/documents">{p.name} {p.version}</Link></div>)}
        </div>
      )}

      <div className="grid c2">
        <div className="card">
          <h3>My projects ({projects.filter((p: any) => ["active", "ending"].includes(p.status)).length} active)</h3>
          {projects.map((p: any) => (
            <div key={p.placement_id} className="alert">
              <Chip status={p.status} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <b>{p.project}</b> · {p.role_title}
                <div className="muted" style={{ fontSize: 12.5 }}>
                  {date(p.start_date)} – {date(p.end_date)} · {Number(p.hours_per_week)} h/week · SOW {p.governing_sow ?? "–"} ends {date(p.sow_end)}
                  {p.pending_extension && <> · <b>Extension in progress:</b> {p.pending_extension}</>}
                </div>
                <div className="chain mt">
                  {p.end_client && p.end_client !== p.customer && <><div className="node"><div className="t">End client</div><div className="n">{p.end_client}</div></div><div className="link"><div className="arr" /></div></>}
                  <div className="node"><div className="t">Customer</div><div className="n">{p.customer}</div></div>
                  <div className="link"><div className="arr" /></div>
                  <div className="node esg"><div className="t">Placed by</div><div className="n">{workspace?.tenant.name ?? "Your staffing company"}</div></div>
                  {p.payee_company && <><div className="link"><div className="arr" /></div><div className="node"><div className="t">Your employer</div><div className="n">{p.payee_company}</div></div></>}
                  <div className="link"><div className="arr" /></div>
                  <div className="node"><div className="t">You</div><div className="n">{me.full_name}</div></div>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="card">
          <h3>Work authorization</h3>
          <dl className="dl">
            <dt>Type</dt><dd>{me.work_auth_type ?? "–"}</dd>
            <dt>Valid until</dt><dd>{me.work_auth_expires ? <>{date(me.work_auth_expires)} <Chip status={authDays! <= 30 ? "due_30" : authDays! <= 120 ? "due_120" : "valid"}>{daysLeft(authDays)}</Chip></> : "–"}</dd>
            <dt>Form I-9</dt><dd>{me.i9_status ?? "–"}</dd>
            <dt>E-Verify</dt><dd>{me.everify_status ?? "–"}</dd>
          </dl>
          {documents.length > 0 && <p className="note">{documents.length} document(s) tracked — you'll get e-mail reminders before anything expires.</p>}
        </div>
      </div>

      <div className="card mt">
        <h3>Where my payments are</h3>
        <p className="muted" style={{ marginTop: -6 }}>Status only. Amounts and rates between companies are private to each contract.</p>
        {payments.length ? (
          <div className="tw"><table>
            <thead><tr><th>Period</th><th>Project</th><th>Hours</th><th>Customer paid us</th><th>We pay {payments[0]?.payee ?? "you"}</th></tr></thead>
            <tbody>{payments.map((p: any, i: number) => (
              <tr key={i}>
                <td>{date(p.period_start)} – {date(p.period_end)}</td>
                <td>{p.project}</td>
                <td className="num">{Number(p.hours)}</td>
                <td><Chip status={p.customer_status} />{p.customer_paid_on ? ` ${date(p.customer_paid_on)}` : p.due_on ? ` due ${date(p.due_on)}` : ""}</td>
                <td>{p.payee_status ? <><Chip status={p.payee_status} />{p.payee_paid_on ? ` ${date(p.payee_paid_on)}` : p.payee_scheduled_on ? ` scheduled ${date(p.payee_scheduled_on)}` : p.payee_due_on ? ` due ${date(p.payee_due_on)}` : ""}</> : me.engagement.startsWith("w2") ? "Payroll" : "Waiting for invoice"}</td>
              </tr>
            ))}</tbody>
          </table></div>
        ) : <p className="muted">No invoices yet. Once your hours are approved and invoiced, you'll see each step here.</p>}
      </div>
    </>
  );
}
