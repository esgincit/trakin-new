"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { DataTable, type Column } from "@/components/DataTable";
import { Chip, ErrorBox, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, label } from "@/lib/format";
import { allows, canEdit as permits, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";
import { addDays, dayLabels, sundayOf } from "@/lib/weeks";

export default function Timesheets() {
  const router = useRouter();
  const { workspace } = useSession();
  const [tab, setTab] = useState<"week" | "history">("week");
  const [week, setWeek] = useState(sundayOf());
  const { data, error, reload } = useApi("/timesheets", { week });
  const history = useApi<any[]>(tab === "history" ? "/timesheets/history" : null);
  // Week holds what still needs an approver; done weeks live in History.
  const completed = (history.data ?? []).filter((r: any) => r.status === "approved");
  const { run, busy } = useAction();
  const canApprove = allows(workspace, "approver", "account_manager", "hr", "finance") && permits(workspace, "timesheets");
  const clientQueue = useApi<any[]>("/timesheets/client-queue");
  const days = dayLabels(week);

  const columns: Column<any>[] = [
    { key: "full_name", label: "Consultant" },
    { key: "engagement", label: "Type", type: "label", filter: true, hideSm: true },
    { key: "projects", label: "Projects", hideSm: true },
    ...days.map((d, i) => ({ key: `d${i}`, label: d, type: "number" as const, hideSm: true, value: (r: any) => r.days[i] })),
    { key: "total", label: "Total", type: "number" },
    { key: "status", label: "Status", type: "status", filter: true },
    { key: "checks", label: "Checks", value: (r: any) => r.checks?.label ?? "",
      render: (r: any) => r.checks ? <Chip status={r.checks.result === "pass" ? "ok" : r.checks.result === "fail" ? "rejected" : "pending"}>{r.checks.label}</Chip> : "–" },
  ];

  const passing = (data?.rows ?? []).filter((r: any) =>
    r.status === "submitted" && !r.placed_by_approved && r.checks?.result === "pass").length;

  return (
    <>
      <PageHead title="Timesheets" sub="Each consultant submits one timesheet per week across all of their projects. Validate and approve here."
        actions={canApprove && tab === "week" && (
          <button className="btn pri" disabled={busy || !passing} onClick={async () => {
            const r = await run(() => api("/timesheets/approve-passing", { method: "POST", query: { week } }));
            if (r) { alert(r.approved.length ? `Approved: ${r.approved.join(", ")}` : "Nothing to approve"); reload(); }
          }}>Approve all that pass ({passing})</button>
        )} />
      <div className="tabs">
        <button className={tab === "week" ? "on" : ""} onClick={() => setTab("week")}>Week</button>
        <button className={tab === "history" ? "on" : ""} onClick={() => setTab("history")}>History</button>
      </div>
      {tab === "week" ? (
        <>
          {!(clientQueue.data ?? []).length ? null : (
            <div className="card mt" style={{ marginBottom: 16 }}>
              <h3>Timesheets waiting for our approval (end client)</h3>
              <div className="tw"><table>
                <thead><tr><th>Week</th><th>Consultant</th><th>Placed by</th><th className="num">Hours</th><th /></tr></thead>
                <tbody>{(clientQueue.data ?? []).map((q: any) => (
                  <tr key={q.timesheet_id}>
                    <td>{date(q.week_start)}</td>
                    <td>{q.consultant}</td>
                    <td>{q.placed_by}</td>
                    <td className="num">{Number(q.total).toFixed(2)}</td>
                    <td><button className="btn sm" disabled={busy} onClick={async () => {
                      const r = await run(() => api(`/timesheets/${q.timesheet_id}/client-link`, { method: "POST" }));
                      if (r?.token) router.push(`/approve/timesheet/${r.token}`);
                    }}>Review &amp; approve</button></td>
                  </tr>
                ))}</tbody>
              </table></div>
            </div>
          )}
          <div className="toolbar">
            <button className="btn sm" onClick={() => setWeek(addDays(week, -7))} aria-label="Previous week">←</button>
            <b>Week of {date(week)}</b>
            <button className="btn sm" onClick={() => setWeek(addDays(week, 7))} aria-label="Next week">→</button>
            <button className="btn sm" onClick={() => setWeek(sundayOf())}>This week</button>
          </div>
          <ErrorBox error={error} retry={reload} />
          <DataTable id="timesheets-week" rows={data?.rows} columns={columns}
                     onRowClick={(r) => r.id ? router.push(`/timesheets/${r.id}`) : undefined}
                     empty="No timesheets are waiting for approval this week." />
        </>
      ) : (
        <DataTable id="timesheets-history" rows={completed} onRowClick={(r) => router.push(`/timesheets/${r.id}`)} columns={[
          { key: "week_start", label: "Week", type: "date" },
          { key: "full_name", label: "Consultant", filter: true },
          { key: "project", label: "Project", filter: true },
          { key: "hours", label: "Hours", type: "number" },
          { key: "status", label: "Status", type: "status", filter: true },
          { key: "decided_at", label: "Decided", type: "date", hideSm: true },
        ]} empty="No approved timesheets yet." />
      )}
      <p className="note">Weeks run Sunday to Saturday. Approved weeks move to History. {label("w2_contract")} and {label("w2_fulltime")} hours over 40 are flagged as overtime.</p>
    </>
  );
}
