"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Chip, ErrorBox, Loading, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, num } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { addDays, dayLabels, sundayOf } from "@/lib/weeks";

type Row = { placement_id: string | null; project: string; hours: number[] };

export default function MyTimesheet() {
  const [week, setWeek] = useState(sundayOf());
  const { data, error, loading, reload } = useApi("/timesheets/mine", { week });
  const history = useApi<any[]>("/me/timesheets");
  const [rows, setRows] = useState<Row[]>([]);
  const [note, setNote] = useState("");
  const { run, busy } = useAction();

  useEffect(() => {
    if (!data) return;
    setRows(data.rows.map((r: any) => ({ ...r, hours: r.hours.map(Number) })));
    setNote(data.note ?? "");
  }, [data]);

  const locked = data && ["submitted", "approved"].includes(data.status);
  const days = dayLabels(week);
  const set = (ri: number, di: number, v: string) =>
    setRows((rs) => rs.map((r, i) => i !== ri ? r : { ...r, hours: r.hours.map((h, j) => (j === di ? Math.max(0, Math.min(24, Number(v) || 0)) : h)) }));
  const dayTotal = (di: number) => rows.reduce((s, r) => s + (r.hours[di] ?? 0), 0);
  const total = rows.reduce((s, r) => s + r.hours.reduce((a, h) => a + h, 0), 0);
  const save = () => api("/timesheets/mine", { method: "PUT", body: { week_start: week, note, rows: rows.map((r) => ({ placement_id: r.placement_id, hours: r.hours })) } });

  return (
    <>
      <PageHead title="My timesheet" sub="One timesheet per week covers every project you work on." />
      <div className="toolbar">
        <button className="btn sm" onClick={() => setWeek(addDays(week, -7))} aria-label="Previous week">←</button>
        <b>Week of {date(week)}</b>
        <button className="btn sm" onClick={() => setWeek(addDays(week, 7))} aria-label="Next week">→</button>
        {data && <Chip status={data.status} />}
      </div>
      {loading ? <Loading /> : error ? <ErrorBox error={error} retry={reload} /> : (
        <>
          {data.reject_reason && <p className="err">Returned by your approver: {data.reject_reason}</p>}
          <div className="tw ts">
            <table>
              <thead><tr><th>Project</th>{days.map((d) => <th key={d}>{d}</th>)}<th className="num">Total</th></tr></thead>
              <tbody>
                {rows.map((r, ri) => (
                  <tr key={r.placement_id ?? "internal"}>
                    <td>{r.project}</td>
                    {r.hours.map((h, di) => (
                      <td key={di}><input type="number" min={0} max={24} step={0.25} value={h || ""} placeholder="0" disabled={locked}
                                         aria-label={`${r.project} ${days[di]}`} onChange={(e) => set(ri, di, e.target.value)} /></td>
                    ))}
                    <td className="num"><b>{num(r.hours.reduce((a, h) => a + h, 0), 2)}</b></td>
                  </tr>
                ))}
                <tr><td><b>Day total</b></td>{days.map((d, di) => <td key={d} className={dayTotal(di) > 12 ? "err" : "muted"}>{num(dayTotal(di), 2)}</td>)}<td className="num"><b>{num(total, 2)}</b></td></tr>
              </tbody>
            </table>
          </div>
          {rows.length === 0 && <p className="muted">No projects are assigned to you for this week.</p>}
          <textarea className="ctl mt" placeholder="Note for your approver (optional)" value={note} onChange={(e) => setNote(e.target.value)} disabled={locked} />
          {!locked && (
            <div className="row mt">
              {!rows.some((r) => r.placement_id === null) && (
                <button className="btn" onClick={() => setRows((rs) => [...rs, { placement_id: null, project: "Internal / non-billable", hours: [0, 0, 0, 0, 0, 0, 0] }])}>Add internal time</button>
              )}
              <span className="grow" style={{ flex: 1 }} />
              <button className="btn" disabled={busy} onClick={async () => { if (await run(save, "Saved")) reload(); }}>Save draft</button>
              <button className="btn pri" disabled={busy || total <= 0} onClick={async () => {
                const ok = await run(async () => { await save(); return api("/timesheets/mine/submit", { body: {}, query: { week } }); }, "Submitted for approval");
                if (ok) { reload(); history.reload(); }
              }}>Submit week</button>
            </div>
          )}
          {locked && <p className="note">This week is {data.status}. Ask your approver to return it if something needs to change.</p>}
        </>
      )}

      <div className="card mt">
        <h3>My timesheet history</h3>
        {history.data?.length ? (
          <div className="tw"><table>
            <thead><tr><th>Week</th><th>Project</th><th className="num">Hours</th><th>Status</th></tr></thead>
            <tbody>{history.data.slice(0, 40).map((h, i) => (
              <tr key={i} className="click" onClick={() => setWeek(h.week_start)}><td>{date(h.week_start)}</td><td>{h.project}</td><td className="num">{num(h.hours, 2)}</td><td><Chip status={h.status} /></td></tr>
            ))}</tbody>
          </table></div>
        ) : <p className="muted">Your submitted weeks will appear here.</p>}
        <p className="note"><Link href="/my">Back to My work</Link></p>
      </div>
    </>
  );
}
