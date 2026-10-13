"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Chip, ErrorBox, Kpi, Loading, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, money } from "@/lib/format";
import { linkFor } from "@/lib/links";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

export default function Dashboard() {
  const { workspace } = useSession();
  const { data, error, loading, reload } = useApi("/dashboard");
  const suggestions = useApi<any[]>("/insights");
  const router = useRouter();

  if (loading) return <Loading rows={8} />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  const k = data.kpis;
  const max = Math.max(1, ...data.forecast.map((f: any) => Math.max(Number(f.in), Number(f.out ?? 0))));

  return (
    <>
      <PageHead title="Dashboard" sub={`${workspace?.tenant.name} · what is owed to you, what you owe, and what needs attention`} />
      <div className="grid k6">
        <Kpi label="Clients owe us (AR)" value={money(k.ar_outstanding, true)} detail={plural(k.ar_open_count, "open invoice")} />
        <Kpi label="Overdue AR" value={money(k.ar_overdue, true)} tone={Number(k.ar_overdue) > 0 ? "bad" : undefined}
             detail={k.ar_overdue_count ? `${plural(k.ar_overdue_count, "invoice")} · oldest ${k.ar_oldest_days} days` : "Nothing overdue"} />
        <Kpi label="Collected, last 30 days" value={money(k.collected_30d, true)} />
        {data.show_ap && <Kpi label="We owe vendors (AP)" value={money(k.ap_outstanding, true)} detail={plural(k.ap_open_count, "open invoice")} />}
        {data.show_ap && <Kpi label="AP on hold" value={money(k.ap_held, true)} tone={Number(k.ap_held) > 0 ? "warn" : undefined} detail="Pay-when-paid or mismatch" />}
        <Kpi label="Contracts ending soon" value={k.contracts_expiring} tone={k.contracts_expiring ? "warn" : undefined} detail="SOWs 60 days · MSAs 90 days" />
      </div>

      <div className="grid c2 mt">
        <div className="card">
          <h3>Smart suggestions</h3>
          {suggestions.data?.length ? suggestions.data.slice(0, 8).map((s, i) => (
            <div key={i} className="alert">
              <Chip status={s.priority >= 85 ? "overdue" : s.priority >= 70 ? "pending" : "open"}>{s.area}</Chip>
              <div style={{ flex: 1, minWidth: 0 }}>
                <b>{s.title}</b>
                <div className="muted" style={{ fontSize: 12.5 }}>{s.detail}{s.amount != null && ` · ${money(s.amount)}`}</div>
              </div>
              <Link className="btn sm" href={s.link}>{s.action}</Link>
            </div>
          )) : <p className="muted">All caught up.</p>}
          <AskBox />
        </div>

        <div className="card">
          <h3>Cash in and out, next 6 weeks</h3>
          <div className="legend"><span><i style={{ background: "var(--brand)" }} />In (client payments due)</span>
            {data.show_ap && <span><i style={{ background: "var(--out)" }} />Out (vendor and 1099 payments)</span>}</div>
          <div className="cf">
            {data.forecast.map((f: any) => (
              <div key={f.bucket} style={{ display: "contents" }}>
                <div className="lbl">{f.bucket === "past_due" ? "Past due" : `Wk of ${date(f.bucket).replace(/, \d{4}$/, "")}`}</div>
                <div className="bars">
                  <div className="b in" style={{ width: `${(Number(f.in) / max) * 100}%` }} />
                  {f.out !== null && <div className="b out" style={{ width: `${(Number(f.out) / max) * 100}%` }} />}
                </div>
                <div className="v"><span>{money(f.in, true)}</span>{f.out !== null && <span className="muted">{money(f.out, true)}</span>}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid c2 mt">
        <div className="card">
          <h3>Needs attention</h3>
          {data.attention.length ? data.attention.map((a: any, i: number) => (
            <div key={i} className="alert click" onClick={() => router.push(linkFor(a.ref_type, a.ref_id))}>
              <Chip status={a.tone === "bad" ? "overdue" : "pending"}>{a.kind.replace(/_/g, " ")}</Chip>
              <div><b>{a.title}</b><div className="muted" style={{ fontSize: 12.5 }}>{a.detail}</div></div>
            </div>
          )) : <p className="muted">Nothing needs attention.</p>}
        </div>
        <div className="card">
          <h3>Timesheets missing for last week</h3>
          {data.missing_timesheets_last_week.length ? (
            <>
              {data.missing_timesheets_last_week.map((c: any) => (
                <div key={c.id} className="alert"><Chip status="not_submitted">Missing</Chip><Link href={`/consultants/${c.id}`}>{c.full_name}</Link></div>
              ))}
              <p className="note">Automatic reminders go out Friday, Monday and Tuesday (with HR copied).</p>
            </>
          ) : <p className="muted">Everyone submitted last week.</p>}
        </div>
      </div>
    </>
  );
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

function AskBox() {
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const { run, busy } = useAction();
  return (
    <form className="row mt" onSubmit={async (e) => {
      e.preventDefault();
      const r = await run(() => api("/insights/ask", { body: { question: q } }));
      if (r) setAnswer(r.answer);
    }}>
      <input className="ctl" style={{ flex: 1 }} placeholder="Ask: what should finance do first today?" value={q} onChange={(e) => setQ(e.target.value)} minLength={3} />
      <button className="btn" disabled={busy || q.length < 3}>Ask</button>
      {answer && <p className="note" style={{ whiteSpace: "pre-wrap", width: "100%" }}>{answer}</p>}
    </form>
  );
}
