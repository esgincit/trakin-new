"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Chip, ErrorBox, Loading, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, label, num } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { addDays, dayLabels, sundayOf } from "@/lib/weeks";

type Row = {
  placement_id: string | null;
  project: string;
  hours: number[];
  timesheet_id: string | null;
  ts_status: string;
  ts_placed_by_approved: boolean;
  ts_end_client_approved: boolean;
  ts_end_client: string | null;
};

export default function MyTimesheet() {
  const [week, setWeek] = useState(sundayOf());
  const { data, error, loading, reload } = useApi("/timesheets/mine", { week });
  const history = useApi<any[]>("/me/timesheets");
  const [rows, setRows] = useState<Row[]>([]);
  const [note, setNote] = useState("");
  const [noteError, setNoteError] = useState("");
  const { run, busy } = useAction();

  // Load the week's saved hours once, and again only when the week changes. A
  // background refresh (the approval-status poll) must never overwrite what the
  // consultant is typing.
  const loadedWeek = useRef<string | null>(null);
  useEffect(() => {
    if (!data || data.week_start !== week || loadedWeek.current === week) return;
    loadedWeek.current = week;
    setRows(data.rows.map((r: any) => ({ ...r, hours: r.hours.map(Number) })));
    setNote(data.note ?? "");
    setNoteError("");
  }, [data, week]);

  // Keep the approval statuses fresh while any timesheet is waiting for the companies.
  useEffect(() => {
    if (!data || data.status !== "submitted") return;
    const iv = setInterval(reload, 15000);
    return () => clearInterval(iv);
  }, [data?.status, week, reload]);

  const days = dayLabels(week);
  const setHours = (ri: number, di: number, v: string) => {
    setRows((rs) =>
      rs.map((r, i) => {
        if (i !== ri) return r;
        const newHours = [...r.hours];
        newHours[di] = Math.max(0, Math.min(24, Number(v) || 0));
        return { ...r, hours: newHours };
      })
    );
  };
  const dayTotal = (di: number) => rows.reduce((s, r) => s + (r.hours[di] ?? 0), 0);
  const total = rows.reduce((s, r) => s + r.hours.reduce((a, h) => a + h, 0), 0);
  const weekendHours = rows.reduce((s, r) => s + (r.hours[5] ?? 0) + (r.hours[6] ?? 0), 0);

  const addInternalTime = () => {
    setRows((rs) => [
      ...rs,
      {
        placement_id: null,
        project: "Internal / non-billable",
        hours: [0, 0, 0, 0, 0, 0, 0],
        timesheet_id: null,
        ts_status: "draft",
        ts_placed_by_approved: false,
        ts_end_client_approved: false,
        ts_end_client: null,
      },
    ]);
  };

  const saveDraft = async () => {
    const body = {
      week_start: week,
      note,
      rows: rows.map((r) => ({ placement_id: r.placement_id, hours: r.hours })),
    };
    if (await api("/timesheets/mine", { method: "PUT", body })) reload();
  };

  const saveAndSubmit = async (ri: number) => {
    const r = rows[ri];
    const body = { week_start: week, note, rows: [{ placement_id: r.placement_id, hours: r.hours }] };
    const target = await run(async () => {
      // Save this project only (the server upserts per placement, so other
      // projects keep their drafts), then submit the timesheet it returns —
      // a brand-new project has no timesheet id until that save.
      const saved: any = await api("/timesheets/mine", { method: "PUT", body });
      const row = (saved?.rows ?? []).find((x: any) => (x.placement_id ?? null) === r.placement_id);
      if (!row?.timesheet_id) throw new Error("This project's hours weren't saved — try again.");
      await api(`/timesheets/${row.timesheet_id}/submit`, { method: "POST", body: {}, query: { week } });
      return row.timesheet_id as string;
    }, `${r.project} submitted for approval`);
    if (!target) return;
    setRows((rs) => rs.map((x, i) => i === ri ? { ...x, timesheet_id: target, ts_status: "submitted" } : x));
    setNoteError("");
    reload();
    history.reload();
  };

  return (
    <>
      <PageHead title="My timesheet" sub="One timesheet per project per week. Submit each project independently." />
      <div className="toolbar">
        <button className="btn sm" onClick={() => setWeek(addDays(week, -7))} aria-label="Previous week">
          ←
        </button>
        <b>Week of {date(week)}</b>
        <button className="btn sm" onClick={() => setWeek(addDays(week, 7))} aria-label="Next week">
          →
        </button>
        {data && <Chip status={data.status} />}
      </div>
      {loading ? <Loading /> : error ? <ErrorBox error={error} retry={reload} /> : (
        <>
          {data.reject_reason && <p className="err">Returned by your approver: {data.reject_reason}</p>}
          <div className="tw ts">
            <table>
              <thead>
                <tr>
                  <th>Project</th>
                  {days.map((d) => <th key={d}>{d}</th>)}
                  <th className="num">Total</th>
                  <th>Placed By</th>
                  <th>End Client</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, ri) => {
                  const locked = r.ts_status === "submitted" || r.ts_status === "approved";
                  const placedBy = data.placed_by_name ? ` — ${data.placed_by_name}` : " (placing company)";
                  const endClient = r.ts_end_client ? ` — ${r.ts_end_client}` : "";
                  return (
                    <tr key={r.placement_id ?? "internal"}>
                      <td>{r.project}</td>
                      {r.hours.map((h, di) => (
                        <td key={di}>
                          <input
                            type="number"
                            min={0}
                            max={24}
                            step={0.25}
                            value={h || ""}
                            placeholder="0"
                            disabled={locked || busy}
                            aria-label={`${r.project} ${days[di]}`}
                            onChange={(e) => setHours(ri, di, e.target.value)}
                          />
                        </td>
                      ))}
                      <td className="num"><b>{num(r.hours.reduce((a, h) => a + h, 0), 2)}</b></td>
                      <td>
                        <Chip status={r.ts_placed_by_approved ? "accepted" : "pending"} />
                        {placedBy}
                      </td>
                      <td>
                        <Chip status={r.ts_end_client_approved ? "accepted" : "pending"} />
                        {endClient}
                      </td>
                      <td>
                        {!locked && (
                          <button
                            className="btn pri sm"
                            disabled={busy || r.hours.reduce((a, h) => a + h, 0) <= 0 || !note.trim()}
                            onClick={() => saveAndSubmit(ri)}
                          >
                            Submit
                          </button>
                        )}
                        {locked && r.ts_status === "submitted" && (
                          <span className="muted" style={{ fontSize: 11 }}>
                            Pending approval
                          </span>
                        )}
                        {locked && r.ts_status === "approved" && (
                          <span className="muted" style={{ fontSize: 11, color: "var(--ok)" }}>
                            Approved
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {data.time_off?.some(Boolean) && (
                  <tr>
                    <td className="muted">Time off (approved)</td>
                    {data.time_off.map((k: string | null, di: number) => (
                      <td key={di} className="muted">
                        {k ? label(k) : ""}
                      </td>
                    ))}
                    <td />
                  </tr>
                )}
                <tr>
                  <td><b>Day total</b></td>
                  {days.map((d, di) => (
                    <td key={d} className={dayTotal(di) > 12 ? "err" : "muted"}>
                      {num(dayTotal(di), 2)}
                    </td>
                  ))}
                  <td className="num"><b>{num(total, 2)}</b></td>
                  <td />
                  <td />
                  <td />
                </tr>
              </tbody>
            </table>
          </div>
          {rows.length === 0 && <p className="muted">No projects are assigned to you for this week.</p>}
          <div className="mt">
            <label htmlFor="tsNote" className="muted" style={{ fontSize: 12.5, display: "block", marginBottom: 4 }}>
              Note for your approver <span style={{ color: "var(--bad)" }} aria-hidden="true">*</span>
              <span className="muted"> — required to submit</span>
            </label>
            <textarea
              id="tsNote"
              className={`ctl ${noteError ? "err" : ""}`}
              placeholder="Explain anything your approver should know about this week"
              value={note}
              onChange={(e) => { setNote(e.target.value); setNoteError(""); }}
              disabled={busy}
              required
            />
            {noteError && <p className="err" style={{ marginTop: 6 }}>{noteError}</p>}
          </div>
          {!busy && (
            <div className="row mt">
              {!rows.some((r) => r.placement_id === null) && (
                <button className="btn" onClick={addInternalTime}>
                  Add internal time
                </button>
              )}
              <span className="grow" style={{ flex: 1 }} />
              <button className="btn" disabled={busy} onClick={saveDraft}>
                Save draft
              </button>
            </div>
          )}
          {busy && <p className="note">Saving…</p>}
          {rows.every((r) => r.ts_status === "submitted" || r.ts_status === "approved") && (
            <p className="note">
              All projects submitted. Ask your approver to return a timesheet if something needs to change.
            </p>
          )}
          {rows.some((r) => r.ts_status === "draft") && !busy && (
            <p className="note">
              Draft projects are not yet submitted. Use the Submit button next to each project's total hours.
            </p>
          )}
        </>
      )}
      <div className="card mt">
        <h3>My timesheet history</h3>
        {history.data?.length ? (
          <div className="tw">
            <table>
              <thead>
                <tr>
                  <th>Week</th>
                  <th>Project</th>
                  <th className="num">Hours</th>
                  <th>Placed By</th>
                  <th>End Client</th>
                </tr>
              </thead>
              <tbody>
                {history.data.slice(0, 40).map((h, i) => (
                  <tr key={i} className="click" onClick={() => setWeek(h.week_start)}>
                    <td>{date(h.week_start)}</td>
                    <td>{h.project}</td>
                    <td className="num">{num(h.hours, 2)}</td>
                    <td>
                      <Chip status={h.status === "rejected" ? "rejected" : h.placed_by_approved ? "accepted" : "pending"} />
                      {h.placed_by_name && <div className="muted" style={{ fontSize: 12 }}>{h.placed_by_name}</div>}
                    </td>
                    <td>
                      <Chip status={h.status === "rejected" ? "rejected" : h.end_client_approved ? "accepted" : "pending"} />
                      {h.end_client_name ? <div className="muted" style={{ fontSize: 12 }}>{h.end_client_name}</div> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">Your submitted weeks will appear here.</p>
        )}
        <p className="note"><Link href="/my">Back to My work</Link></p>
      </div>
    </>
  );
}
