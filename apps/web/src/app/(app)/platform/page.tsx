"use client";

import { useState } from "react";
import { DataTable } from "@/components/DataTable";
import { Chip, Drawer, ErrorBox, Field, formValues, Kpi, Loading, Modal, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, dateTime, label, money } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

type Tab = "overview" | "companies" | "queue" | "admins";
const num = (v: unknown) => Number(v ?? 0);

/** For the team running myTrakIn: platform analytics, every company, the activation queue and platform admins. */
export default function Platform() {
  const metrics = useApi("/platform/metrics");
  const tenants = useApi<any[]>("/platform/tenants");
  const queue = useApi<any[]>("/platform/companies?status=pending");
  const admins = useApi<any[]>("/platform/admins");
  const [tab, setTab] = useState<Tab>("overview");
  const [openTenant, setOpenTenant] = useState<any>(null);
  const [review, setReview] = useState<any>(null);

  if (metrics.loading) return <Loading rows={8} />;
  if (metrics.error) return <ErrorBox error={metrics.error} retry={metrics.reload} />;
  const m = metrics.data;
  const reloadAll = () => { metrics.reload(); tenants.reload(); queue.reload(); admins.reload(); };
  const waiting = num(m.companies.pending_activation);

  return (
    <>
      <PageHead title="Platform admin" sub="Every company on myTrakIn, how the platform is growing, and the money moving through it." />
      <div className="tabs">
        <button className={tab === "overview" ? "on" : ""} onClick={() => setTab("overview")}>Overview</button>
        <button className={tab === "companies" ? "on" : ""} onClick={() => setTab("companies")}>Companies</button>
        <button className={tab === "queue" ? "on" : ""} onClick={() => setTab("queue")}>Waiting for activation{waiting ? ` (${waiting})` : ""}</button>
        <button className={tab === "admins" ? "on" : ""} onClick={() => setTab("admins")}>Platform admins</button>
      </div>

      {tab === "overview" && <Overview m={m} openQueue={() => setTab("queue")} />}

      {tab === "companies" && (
        <DataTable id="platform-companies" rows={tenants.data} onRowClick={setOpenTenant} columns={[
          { key: "name", label: "Company" }, { key: "plan", label: "Plan", type: "label", filter: true },
          { key: "status", label: "Status", type: "status", filter: true },
          { key: "active_users", label: "Users", type: "number" }, { key: "consultants", label: "Consultants", type: "number", hideSm: true },
          { key: "mrr", label: "MRR", type: "money" },
          { key: "ar_invoiced", label: "Invoiced", type: "money", hideSm: true },
          { key: "ar_collected", label: "Collected", type: "money", hideSm: true },
          { key: "ap_paid", label: "Paid to vendors", type: "money", hideSm: true },
          { key: "last_user_activity", label: "Last active", render: (r) => dateTime(r.last_user_activity), value: (r) => r.last_user_activity },
          { key: "created_at", label: "Created", type: "date", hideSm: true },
        ]} />
      )}

      {tab === "queue" && (
        queue.data?.length ? (
          <DataTable id="platform-queue" rows={queue.data} onRowClick={setReview} columns={[
            { key: "name", label: "Company" }, { key: "owner_name", label: "Owner" }, { key: "owner_email", label: "Owner e-mail" },
            { key: "country", label: "Country", hideSm: true }, { key: "kind", label: "Type", type: "label", hideSm: true },
            { key: "w9_status", label: "W-9", type: "status", hideSm: true },
            { key: "decision_note", label: "Last note", hideSm: true },
            { key: "created_at", label: "Registered", type: "date" },
          ]} />
        ) : <p className="muted">No companies are waiting for activation.</p>
      )}

      {tab === "admins" && <Admins rows={admins.data ?? []} reload={admins.reload} />}

      <TenantDrawer tenant={openTenant} onClose={() => setOpenTenant(null)} onSaved={() => { setOpenTenant(null); reloadAll(); }} />
      {review && <Review row={review} onClose={() => setReview(null)} onDone={() => { setReview(null); reloadAll(); }} />}
    </>
  );
}

function Overview({ m, openQueue }: { m: any; openQueue: () => void }) {
  const pipeMax = Math.max(1, ...m.pipeline.map((p: any) => num(p.count)));
  const trendMax = Math.max(1, ...m.money.trend.flatMap((t: any) => [num(t.invoiced), num(t.collected)]));
  return (
    <>
      <div className="grid k4">
        <Kpi label="Total users" value={m.users.total} detail={`${m.users.new_30d} new · ${m.users.active_30d} active in 30 days`} />
        <Kpi label="Companies" value={m.companies.total} detail={`${m.companies.active} active · ${m.companies.pending_activation} waiting · ${m.companies.new_30d} new in 30 days`}
          tone={m.companies.pending_activation ? "warn" : undefined} />
        <Kpi label="MRR" value={money(m.revenue.mrr, true)} detail={`ARR ${money(m.revenue.arr, true)} · ${m.revenue.paying_companies} paying`} />
        <Kpi label="Revenue per user" value={money(m.revenue.arpu)} detail={`${m.activity.consultants} consultants · ${m.activity.active_placements} placements`} />
      </div>
      <h3 className="mt">Money moving through myTrakIn</h3>
      <div className="grid k4">
        <Kpi label="Invoiced to clients" value={money(m.money.ar_invoiced, true)} detail={`${money(m.money.invoiced_30d, true)} in the last 30 days`} />
        <Kpi label="Collected" value={money(m.money.ar_collected, true)} detail={`${money(m.money.collected_30d, true)} in the last 30 days`} />
        <Kpi label="Outstanding from clients" value={money(m.money.ar_outstanding, true)} />
        <Kpi label="Paid to vendors" value={money(m.money.ap_paid, true)} detail={`of ${money(m.money.ap_billed, true)} billed`} />
      </div>

      <div className="grid c2 mt">
        <div className="card">
          <h3>Onboarding pipeline</h3>
          <div className="cf">
            {m.pipeline.map((p: any) => (
              <div key={p.stage} style={{ display: "contents" }}>
                <div className="lbl">{p.stage === "Waiting for activation" && num(p.count) > 0
                  ? <a onClick={openQueue}>{p.stage}</a> : p.stage}</div>
                <div className="bars" title={`${p.stage}: ${p.count}`}>
                  <div className="b in" style={{ width: `${(num(p.count) / pipeMax) * 100}%`, minWidth: num(p.count) ? 4 : 0 }} />
                </div>
                <div className="v"><span>{p.count}</span></div>
              </div>
            ))}
          </div>
          {m.companies.inactive_14_days.length > 0 && (
            <p className="note mt">No activity for 14+ days: {m.companies.inactive_14_days.join(", ")}</p>
          )}
        </div>

        <div className="card">
          <h3>Client invoicing and collections, last 12 months</h3>
          <div className="legend"><span><i style={{ background: "var(--brand)" }} />Invoiced</span>
            <span><i style={{ background: "var(--out)" }} />Collected</span></div>
          <div className="cf">
            {m.money.trend.map((t: any) => (
              <div key={t.month} style={{ display: "contents" }}>
                <div className="lbl">{t.month}</div>
                <div className="bars" title={`${t.month} — invoiced ${money(t.invoiced)}, collected ${money(t.collected)}`}>
                  <div className="b in" style={{ width: `${(num(t.invoiced) / trendMax) * 100}%` }} />
                  <div className="b out" style={{ width: `${(num(t.collected) / trendMax) * 100}%` }} />
                </div>
                <div className="v"><span>{money(t.invoiced, true)}</span><span className="muted">{money(t.collected, true)}</span></div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card mt">
        <h3>Subscription revenue by plan</h3>
        <dl className="dl">
          {Object.entries(m.revenue.by_plan).map(([plan, v]) => <div key={plan} style={{ display: "contents" }}><dt>{label(plan)}</dt><dd>{money(v as any)} / month</dd></div>)}
        </dl>
      </div>
    </>
  );
}

function TenantDrawer({ tenant, onClose, onSaved }: { tenant: any; onClose: () => void; onSaved: () => void }) {
  const { run, busy } = useAction();
  return (
    <Drawer open={!!tenant} onClose={onClose} title={tenant?.name ?? ""}>
      {tenant && (
        <>
          <dl className="dl">
            <dt>Status</dt><dd><Chip status={tenant.status} /></dd><dt>Plan</dt><dd>{label(tenant.plan)} · {money(tenant.price_per_user)}/user/month</dd>
            <dt>Trial ends</dt><dd>{date(tenant.trial_ends_on)}</dd><dt>Activated</dt><dd>{date(tenant.activated_at)}</dd>
            <dt>Users</dt><dd>{tenant.active_users} active · {tenant.invited_users} invited</dd><dt>MRR</dt><dd>{money(tenant.mrr)}</dd>
            <dt>Invoiced / collected</dt><dd>{money(tenant.ar_invoiced)} / {money(tenant.ar_collected)}</dd>
            <dt>Vendor bills / paid</dt><dd>{money(tenant.ap_billed)} / {money(tenant.ap_paid)}</dd>
          </dl>
          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            if (await run(() => api(`/platform/tenants/${tenant.id}`, { method: "PATCH", body: formValues(e.currentTarget) }), "Saved")) onSaved();
          }}>
            <Field label="Plan" name="plan" as="select" defaultValue={tenant.plan} options={["starter", "growth", "enterprise"]} />
            <Field label="Status" name="status" as="select" defaultValue={tenant.status} options={[["onboarding", "Waiting for activation"], ["active", "Active"], ["suspended", "Suspended (no sign-in)"], ["closed", "Closed"]]} />
            <Field label="Trial ends" name="trial_ends_on" type="date" defaultValue={tenant.trial_ends_on ?? ""} />
            <button className="btn pri mt" disabled={busy}>Save</button>
          </form>
          <form className="form mt" onSubmit={async (e) => {
            e.preventDefault();
            if (await run(() => api(`/platform/companies/${tenant.id}/owner`, { body: formValues(e.currentTarget) }), "Owner changed")) onSaved();
          }}>
            <h3>Change the owner</h3>
            <p className="muted">For when the owner has left. The new owner must already be an active user of this company.</p>
            <Field label="New owner's e-mail" name="email" type="email" required />
            <button className="btn mt" disabled={busy}>Make owner</button>
          </form>
        </>
      )}
    </Drawer>
  );
}

function Review({ row, onClose, onDone }: { row: any; onClose: () => void; onDone: () => void }) {
  const detail = useApi<any>(`/platform/companies/${row.tenant_id}`);
  const { run, busy } = useAction();
  const [note, setNote] = useState("");
  const decide = async (decision: "activate" | "needs_info" | "reject", msg: string) => {
    if (await run(() => api(`/platform/companies/${row.tenant_id}/decision`, { body: { decision, note: note || null } }), msg)) onDone();
  };
  const c = detail.data?.company;
  return (
    <Drawer open onClose={onClose} title={row.name}>
      {detail.loading ? <Loading /> : detail.error ? <ErrorBox error={detail.error} retry={detail.reload} /> : (
        <>
          <dl className="dl">
            <dt>Owner</dt><dd>{row.owner_name ?? "–"} · {row.owner_email}</dd>
            <dt>Business ID</dt><dd><code>{c.business_code}</code></dd>
            <dt>Type</dt><dd>{label(c.kind)} · {c.country}</dd>
            <dt>Legal name</dt><dd>{c.name}{c.dba ? ` (DBA ${c.dba})` : ""}</dd>
            <dt>{c.country === "IN" ? "CIN" : "TIN"}</dt><dd>{c.cin ?? c.tin ?? "–"}</dd>
            <dt>Tax class</dt><dd>{c.tax_classification ?? "–"}</dd>
            <dt>Address</dt><dd>{c.tax_address ?? c.address ?? "–"}</dd>
            <dt>Domain / e-mail</dt><dd>{c.domain ?? "–"} · {c.contact_email ?? "–"}</dd>
            <dt>W-9</dt><dd><Chip status={c.w9_status} /> {detail.data.w9_url && <a href={detail.data.w9_url} target="_blank" rel="noreferrer">View W-9</a>}</dd>
            <dt>Registered</dt><dd>{dateTime(c.created_at)}</dd>
          </dl>
          <h3 className="mt">Checks</h3>
          {Object.entries(detail.data.checks ?? {}).filter(([, v]: [string, any]) => v?.status).map(([k, v]: [string, any]) => (
            <div key={k} className="alert"><Chip status={v.status === "pass" ? "active" : v.status === "warn" ? "pending" : "overdue"}>{v.status}</Chip>
              <b>{label(k)}</b><span className="muted">{v.detail}</span></div>
          ))}
          {detail.data.blockers?.length > 0 && <p className="note">Still blocking: {detail.data.blockers.join("; ")}. Activating verifies the W-9 you reviewed here.</p>}
          <label className="mt" style={{ display: "block" }}>Note to the owner (needed to ask for more or to reject)
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} style={{ width: "100%" }} />
          </label>
          <div className="row mt">
            <button className="btn pri" disabled={busy} onClick={() => decide("activate", "Activated — the owner has been e-mailed")}>Activate</button>
            <button className="btn" disabled={busy || !note.trim()} onClick={() => decide("needs_info", "Asked the owner for more")}>Ask for more info</button>
            <button className="btn" disabled={busy || !note.trim()} onClick={() => decide("reject", "Rejected")}>Reject</button>
          </div>
        </>
      )}
    </Drawer>
  );
}

function Admins({ rows, reload }: { rows: any[]; reload: () => void }) {
  const { run, busy } = useAction();
  const { me } = useSession();
  const [adding, setAdding] = useState(false);
  return (
    <>
      <div className="row" style={{ justifyContent: "flex-end" }}><button className="btn pri" onClick={() => setAdding(true)}>Add platform admin</button></div>
      <DataTable id="platform-admins" rows={rows} columns={[
        { key: "full_name", label: "Name" }, { key: "email", label: "E-mail" },
        { key: "user_id", label: "", render: (r) => r.user_id === me?.profile.id ? <span className="muted">You</span> : (
          <button className="btn sm" disabled={busy} onClick={async (e) => {
            e.stopPropagation();
            if (await run(() => api(`/platform/admins/${r.user_id}`, { method: "DELETE" }), "Removed")) reload();
          }}>Remove</button>) },
      ]} />
      {adding && (
        <Modal title="Add a platform admin" onClose={() => setAdding(false)}>
          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            if (await run(() => api("/platform/admins", { body: formValues(e.currentTarget) }), "Platform admin added")) { setAdding(false); reload(); }
          }}>
            <p className="muted">They get the full platform console: every company, activation and analytics. They must have signed in to myTrakIn once.</p>
            <Field label="E-mail" name="email" type="email" required full />
            <button className="btn pri mt" disabled={busy}>Add</button>
          </form>
        </Modal>
      )}
    </>
  );
}
