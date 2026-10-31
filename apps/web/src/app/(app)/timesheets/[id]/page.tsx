"use client";

import { useParams, useRouter } from "next/navigation";
import { Chip, ErrorBox, Loading, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, label, money, num } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";
import { dayLabels } from "@/lib/weeks";

export default function TimesheetReview() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { workspace } = useSession();
  const { data: ts, error, loading, reload } = useApi(`/timesheets/${id}`);
  const { run, busy } = useAction();
  const canApprove = allows(workspace, "approver", "account_manager", "hr", "finance");
  if (loading) return <Loading rows={6} />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  // The end client's representative (invited into the placing workspace as a member of
  // their company) approves the second step, after the placing company has approved.
  const canEndApprove = !!ts.awaiting_end_client && !!workspace?.company_id &&
    (ts.end_client_companies ?? []).includes(workspace.company_id);
  const days = dayLabels(ts.week_start);
  const total = ts.rows.reduce((s: number, r: any) => s + r.hours.reduce((a: number, h: any) => a + Number(h), 0), 0);
  const weekendHours = ts.rows.reduce((s: number, r: any) => s + Number(r.hours[5] ?? 0) + Number(r.hours[6] ?? 0), 0);

  return (
    <>
      <PageHead title={`${ts.full_name} · week of ${date(ts.week_start)}`}
        sub={<>{label(ts.engagement)}{ts.employer && ` via ${ts.employer}`} · <Chip status={ts.status} /> · {ts.summary.label}</>}
        actions={<>
          <button className="btn" onClick={() => router.back()}>Back</button>
          {canApprove && ["submitted", "approved"].includes(ts.status) && (
            <button className="btn" disabled={busy} onClick={async () => {
              const approved = ts.status === "approved";
              const reason = prompt(approved ? "What needs to change? The consultant corrects the week and it comes back to you for approval."
                                             : "What should the consultant fix? They'll see this message.");
              if (reason && await run(() => api(`/timesheets/${id}/reject`, { body: { reason } }),
                                      approved ? "Adjustment opened — changes need approval again" : "Returned to the consultant")) reload();
            }}>{ts.status === "approved" ? "Request adjustment" : "Return for changes"}</button>
          )}
          {canApprove && ts.status === "submitted" && !ts.placed_by_approved && weekendHours > 0 && !ts.weekend_confirmed && (
            <button className="btn" disabled={busy} onClick={async () => {
              const note = prompt("Optional note for the consultant (e.g. why the weekend hours need confirming):") ?? "";
              if (await run(() => api(`/timesheets/${id}/weekend-confirm-request`, { body: { note } }),
                              "Asked the consultant to confirm the weekend hours")) reload();
            }}>Ask consultant to confirm weekend hours</button>
          )}
          {canApprove && ts.status === "submitted" && !ts.placed_by_approved && (
            <button className="btn pri" disabled={busy} onClick={async () => {
              if (await run(() => api(`/timesheets/${id}/approve`, { method: "POST" }), "Approved")) reload();
            }}>Approve</button>
          )}
          {!canApprove && canEndApprove && (
            <button className="btn pri" disabled={busy} onClick={async () => {
              if (await run(() => api(`/timesheets/${id}/approve`, { method: "POST" }), "Approved")) reload();
            }}>Approve (end client)</button>
          )}
        </>} />

      {ts.status === "submitted" && ts.placed_by_approved && (
        <p className="note" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <Chip status="accepted">Approved by your company</Chip>
          <span>{ts.awaiting_end_client
            ? "Waiting for the end client's approval — nothing left to approve here."
            : "The approval is recorded."}</span>
        </p>
      )}

      <div className="tw ts">
        <table>
          <thead><tr><th>Project</th>{days.map((d) => <th key={d} className="num">{d}</th>)}<th className="num">Total</th></tr></thead>
          <tbody>
            {ts.rows.map((r: any) => (
              <tr key={r.placement_id ?? "internal"}>
                <td>{r.project}</td>
                {r.hours.map((h: any, i: number) => <td key={i} className="num">{Number(h) ? num(h, 2) : "–"}</td>)}
                <td className="num"><b>{num(r.hours.reduce((a: number, h: any) => a + Number(h), 0), 2)}</b></td>
              </tr>
            ))}
            <tr><td><b>Total</b></td>{days.map((d) => <td key={d} />)}<td className="num"><b>{num(total, 2)}</b></td></tr>
          </tbody>
        </table>
      </div>
      {ts.note && <p className="note">Consultant's note: {ts.note}</p>}
      {weekendHours > 0 && (
        <p className="note">Weekend hours: {num(weekendHours, 2)} h — {ts.weekend_confirmed
          ? "confirmed by the consultant, safe to approve."
          : ts.weekend_requested_at ? "waiting for the consultant to confirm (approval is blocked until they do)."
          : "not confirmed yet — ask the consultant to confirm before approving."}</p>
      )}
      {ts.reject_reason && <p className="err">Returned: {ts.reject_reason}</p>}
      {ts.status === "approved" && <p className="note">Approved{ts.decided_at && ` on ${date(ts.decided_at)}`}. Locked — once invoiced, corrections go on the invoice as a credit note or an extra invoice.</p>}

      <div className="grid c2 mt">
        <div className="card">
          <h3>Checks</h3>
          {ts.checks.map((c: any) => (
            <div key={c.key} className="alert">
              <Chip status={c.result === "pass" ? "ok" : c.result === "fail" ? "rejected" : "pending"}>{c.result}</Chip>
              <div><b>{c.label}</b><div className="muted" style={{ fontSize: 12.5 }}>{c.detail}</div></div>
            </div>
          ))}
        </div>
        {ts.creates && (
          <div className="card">
            <h3>What approval creates</h3>
            <div className="split">
              <div><small>Client invoice (AR) to {ts.creates.ar_to.join(", ") || "–"}</small><b>{money(ts.creates.ar_amount)}</b></div>
              {ts.creates.ap_to.length
                ? <div><small>Payable (AP) to {ts.creates.ap_to.join(", ")}</small><b>{money(ts.creates.ap_amount)}</b></div>
                : <div><small>No AP payable</small><b>W-2 payroll</b></div>}
            </div>
            <p className="note">Only your own two links. Other layers of the chain are never shown or stored.</p>
          </div>
        )}
      </div>
    </>
  );
}
