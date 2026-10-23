"use client";

import Link from "next/link";
import { useState } from "react";
import { ErrorBox, Loading, PageHead } from "@/components/ui";
import { date, label, money, tone } from "@/lib/format";
import { useApi } from "@/lib/useApi";

/**
 * The payment chain, one card per consultant and period. Only the tenant's own two links
 * carry amounts (AR: what the customer owes us; AP: what we owe the vendor or contractor).
 * The end client is shown by name with a masked amount — the tenant isn't party to that contract.
 */
export default function PaymentFlow() {
  const [open, setOpen] = useState(true);
  const [q, setQ] = useState("");
  const { data, error, loading, reload } = useApi<any[]>("/payment-flow", { only_open: open });

  if (error) return <ErrorBox error={error} retry={reload} />;
  const rows = (data ?? []).filter((r) => !q || JSON.stringify(r).toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <PageHead title="Payment flow" sub="Where each payment is in the chain. Only your AR and AP amounts are shown; other layers stay private." />
      <div className="legend">
        <span><i style={{ background: "var(--good)" }} />Paid</span><span><i style={{ background: "var(--brand)" }} />Open / scheduled</span>
        <span><i style={{ background: "var(--warn)" }} />On hold</span><span><i style={{ background: "var(--bad)" }} />Overdue / mismatch</span>
        <span><i style={{ border: "1px dashed var(--muted)" }} />Not your contract (masked)</span>
      </div>
      <div className="toolbar">
        <input className="ctl" type="search" placeholder="Search consultant, customer, invoice…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="seg">
          <button className={open ? "on" : ""} onClick={() => setOpen(true)}>Open</button>
          <button className={!open ? "on" : ""} onClick={() => setOpen(false)}>All</button>
        </div>
      </div>
      {loading ? <Loading /> : (
        <div className="card" style={{ padding: 0 }}>
          {rows.length === 0 && <p className="empty">Nothing open. Every invoice in the chain is settled.</p>}
          {rows.map((r) => r.is_client_flow ? (
            <div key={r.flow_key} className="cyc">
              <div>
                <b>{r.consultant}</b>
                <div className="muted" style={{ fontSize: 12.5 }}>{r.project} · {date(r.period_start)} – {date(r.period_end)}</div>
                <div className="muted" style={{ fontSize: 12.5 }}>{Number(r.hours)} h · {label(r.engagement)}</div>
              </div>
              <div className="pipe">
                <div className={`hop ${tone(r.ap_status)}`}>
                  <div className="who">You → {r.payee}</div>
                  <div className="amt">{money(r.ap_amount)}</div>
                  <div className="st">{label(r.ap_status)}{Number(r.ap_balance) > 0 && r.ap_status !== "paid" ? ` · due ${date(r.ap_due)}` : ""}</div>
                </div>
              </div>
            </div>
          ) : (
            <div key={r.ar_id} className="cyc">
              <div>
                <b>{r.consultant}</b>
                <div className="muted" style={{ fontSize: 12.5 }}>{r.project} · {date(r.period_start)} – {date(r.period_end)}</div>
                <div className="muted" style={{ fontSize: 12.5 }}>{Number(r.hours)} h · {label(r.engagement)}</div>
              </div>
              <div className="pipe">
                {r.end_client && r.end_client !== r.customer && (
                  <div className="hop mute">
                    <div className="who">{r.end_client} → {r.customer}</div>
                    <div className="amt masked">••••</div>
                    <div className="st">Not tracked</div>
                  </div>
                )}
                <Link href={`/invoices/${r.ar_id}`} className={`hop ${tone(r.ar_status)}`} style={{ color: "inherit", fontWeight: 400 }}>
                  <div className="who">{r.customer} → you · AR {r.ar_number}</div>
                  <div className="amt">{money(r.ar_amount)}</div>
                  <div className="st">{label(r.ar_status)}{Number(r.ar_balance) > 0 && r.ar_status !== "paid" ? ` · due ${date(r.ar_due)}` : ""}</div>
                </Link>
                {r.ap_id ? (
                  <Link href={`/invoices/${r.ap_id}`} className={`hop ${tone(r.ap_status)}`} style={{ color: "inherit", fontWeight: 400 }}>
                    <div className="who">You → {r.payee} · AP {r.ap_number}</div>
                    <div className="amt">{money(r.ap_amount)}</div>
                    <div className="st">{label(r.ap_status)}{r.ap_due ? ` · ${date(r.ap_due)}` : ""}</div>
                  </Link>
                ) : (
                  <div className="hop mute">
                    <div className="who">{r.engagement?.startsWith("w2") ? "W-2 payroll" : "No vendor invoice yet"}</div>
                    <div className="amt">–</div>
                    <div className="st">{r.engagement?.startsWith("w2") ? "Paid through payroll" : "Waiting for invoice"}</div>
                  </div>
                )}
              </div>
              <div className="num">
                <div className="muted" style={{ fontSize: 12 }}>Gap AR − AP</div>
                <b>{r.ap_amount == null || r.ar_amount == null ? "••••" : money(Number(r.ar_amount) - Number(r.ap_amount))}</b>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
