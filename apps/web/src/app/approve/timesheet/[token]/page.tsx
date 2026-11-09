"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Chip } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { date, num } from "@/lib/format";

/** The public end-client approval page. No account needed: the link identifies the approver. */
export default function TimesheetApprovalPage() {
  const { token } = useParams<{ token: string }>();
  const base = `/public/ts-approvals/${token}`;
  const [view, setView] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setView(await api(base, { auth: false }));
    } catch (e) {
      setError((e as ApiError).message);
    }
  }, [base]);

  useEffect(() => { load(); }, [load]);

  const decide = async (decision: "approve" | "return") => {
    if (note.trim().length < 3) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api(`${base}/${decision}`, { body: decision === "return" ? { note: note.trim() } : {}, auth: false });
      setDone(decision === "approve"
        ? "Approved. Invoice generation for the week has been triggered — thank you."
        : "The week was returned to the consultant with your note.");
      void r;
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  if (done) return <Shell><h2>Thank you</h2><p>{done}</p><p className="muted">You can close this window.</p></Shell>;
  if (!view) return <Shell>{error ? <><h2>This link doesn't work</h2><p className="muted">{error}</p></> : <div className="skel" />}</Shell>;

  const open = view.status === "submitted";
  const total = view.rows?.reduce((s: number, r: any) => s + r.hours.reduce((a: number, h: any) => a + Number(h.h), 0), 0) ?? view.total_hours;

  return (
    <Shell>
      <div className="row"><h2 style={{ flex: 1 }}>Timesheet — {view.consultant}</h2><Chip status={open ? "submitted" : view.status} /></div>
      <p className="muted">Week of {date(view.week_start)} · placed by {view.placed_by}{view.placed_by_approved ? " (approved)" : ""}{view.expires_at ? ` · link valid until ${date(view.expires_at)}` : ""}</p>
      {view.note && <p className="note">Consultant's note: {view.note}</p>}
      <p className="muted">{num(total, 2)} hours total</p>

      <div className="tw ts">
        <table>
          <thead><tr><th>Project</th><th>Day · hours</th></tr></thead>
          <tbody>
            {view.rows.map((r: any, i: number) => (
              <tr key={i}><td>{r.project}</td>
                <td>{r.hours.filter((h: any) => Number(h.h) > 0).map((h: any) => `${h.d.slice(5)}: ${num(h.h, 2)}`).join(" · ")}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      {open ? (
        <>
          <div className="card mt">
            <label className="muted" style={{ fontSize: 12.5 }} htmlFor="ts-note">Note <span style={{ color: "var(--bad)" }}>*</span></label>
            <textarea id="ts-note" className="ctl mt" placeholder="Add a short note (required)" value={note} onChange={(e) => setNote(e.target.value)} />
            <div className="row mt">
              <button className="btn pri" disabled={busy || note.trim().length < 3} onClick={() => decide("approve")}>Approve timesheet</button>
              <button className="btn" disabled={busy || note.trim().length < 3} onClick={() => decide("return")}>Return with note</button>
            </div>
            <p className="note">Approving finalises this week and triggers invoice generation for both sides of the placement.</p>
          </div>
        </>
      ) : (
        <p className="muted mt">This week isn't awaiting approval ({view.status.replace("_", " ")}). Nothing to do.</p>
      )}
      {error && <p className="err mt" role="alert">{error}</p>}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="auth">
      <div className="logo" style={{ justifyContent: "center", fontSize: 18 }}><i>mT</i>myTrakIn timesheet approval</div>
      <div className="card">{children}</div>
      <p className="muted" style={{ textAlign: "center", fontSize: 12.5 }}>Secured by myTrakIn · Your link is personal; please don't forward it.</p>
    </div>
  );
}
