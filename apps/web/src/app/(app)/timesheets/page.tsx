"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { DataTable, type Column } from "@/components/DataTable";
import { Chip, ErrorBox, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, label } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";
import { addDays, dayLabels, sundayOf } from "@/lib/weeks";

export default function Timesheets() {
  const router = useRouter();
  const { workspace } = useSession();
  const [tab, setTab] = useState<"week" | "history">("week");
  const [week, setWeek] = useState(sundayOf());
  const { data, error, reload } = useApi("/timesheets", { week });
  const history = useApi<any[]>(tab === "history" ? "/timesheets/history" : null);
  const { run, busy } = useAction();
  const canApprove = allows(workspace, "approver", "account_manager", "hr", "finance");
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

  const passing = (data?.rows ?? []).filter((r: any) => r.status === "submitted" && r.checks?.result === "pass").length;

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
          <div className="toolbar">
            <button className="btn sm" onClick={() => setWeek(addDays(week, -7))} aria-label="Previous week">←</button>
            <b>Week of {date(week)}</b>
            <button className="btn sm" onClick={() => setWeek(addDays(week, 7))} aria-label="Next week">→</button>
            <button className="btn sm" onClick={() => setWeek(sundayOf())}>This week</button>
          </div>
          <ErrorBox error={error} retry={reload} />
          <DataTable id="timesheets-week" rows={data?.rows} columns={columns}
                     onRowClick={(r) => r.id ? router.push(`/timesheets/${r.id}`) : undefined}
                     empty="No one is scheduled to work this week." />
        </>
      ) : (
        <DataTable id="timesheets-history" rows={history.data} onRowClick={(r) => router.push(`/timesheets/${r.id}`)} columns={[
          { key: "week_start", label: "Week", type: "date" },
          { key: "full_name", label: "Consultant", filter: true },
          { key: "project", label: "Project", filter: true },
          { key: "hours", label: "Hours", type: "number" },
          { key: "status", label: "Status", type: "status", filter: true },
          { key: "decided_at", label: "Decided", type: "date", hideSm: true },
        ]} />
      )}
      <p className="note">Weeks run Sunday to Saturday. {label("w2_contract")} and {label("w2_fulltime")} hours over 40 are flagged as overtime.</p>
    </>
  );
}
