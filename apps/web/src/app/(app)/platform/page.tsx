"use client";

import { useState } from "react";
import { DataTable } from "@/components/DataTable";
import { Chip, Drawer, ErrorBox, Field, formValues, Kpi, Loading, Modal, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { date, dateTime, label, money } from "@/lib/format";
import { useApi } from "@/lib/useApi";

/** For the company running myTrakIn: tenants, growth, revenue per user, and sign-up approvals. */
export default function Platform() {
  const metrics = useApi("/platform/metrics");
  const tenants = useApi<any[]>("/platform/tenants");
  const signups = useApi<any[]>("/platform/signups");
  const [tab, setTab] = useState<"tenants" | "signups">("tenants");
  const [creating, setCreating] = useState(false);
  const [openTenant, setOpenTenant] = useState<any>(null);
  const [openSignup, setOpenSignup] = useState<any>(null);
  const { run, busy } = useAction();

  if (metrics.loading) return <Loading rows={8} />;
  if (metrics.error) return <ErrorBox error={metrics.error} />;
  const m = metrics.data;
  const reloadAll = () => { metrics.reload(); tenants.reload(); signups.reload(); };

  return (
    <>
      <PageHead title="Owner console" sub="Every workspace on myTrakIn, how each is progressing, and revenue per user." actions={<button className="btn pri" onClick={() => setCreating(true)}>Create workspace</button>} />
      <div className="grid k6">
        <Kpi label="Workspaces" value={m.tenants} detail={`${m.by_status.active} live · ${m.by_status.onboarding} onboarding`} />
        <Kpi label="Active users" value={m.active_users} />
        <Kpi label="MRR" value={money(m.mrr, true)} detail={`ARR ${money(m.arr, true)}`} />
        <Kpi label="Revenue per user" value={money(m.arpu)} detail={`${m.paying_tenants} paying workspaces`} />
        <Kpi label="New, last 30 days" value={m.new_last_30_days} />
        <Kpi label="Sign-ups waiting" value={m.signups.pending ?? 0} tone={m.signups.pending ? "warn" : undefined} />
      </div>
      {m.inactive_14_days.length > 0 && <p className="note">No activity for 14+ days: {m.inactive_14_days.join(", ")}</p>}
      <div className="tabs mt">
        <button className={tab === "tenants" ? "on" : ""} onClick={() => setTab("tenants")}>Workspaces</button>
        <button className={tab === "signups" ? "on" : ""} onClick={() => setTab("signups")}>Sign-up requests</button>
      </div>
      {tab === "tenants" ? (
        <DataTable id="platform-tenants" rows={tenants.data} onRowClick={setOpenTenant} columns={[
          { key: "name", label: "Workspace" }, { key: "plan", label: "Plan", type: "label", filter: true },
          { key: "status", label: "Status", type: "status", filter: true },
          { key: "onboarding_step", label: "Setup", value: (r) => `${r.onboarding_step}/8` },
          { key: "active_users", label: "Users", type: "number" }, { key: "consultants", label: "Consultants", type: "number" },
          { key: "active_placements", label: "Placements", type: "number", hideSm: true }, { key: "mrr", label: "MRR", type: "money" },
          { key: "last_user_activity", label: "Last active", render: (r) => dateTime(r.last_user_activity), value: (r) => r.last_user_activity },
          { key: "created_at", label: "Created", type: "date", hideSm: true },
        ]} />
      ) : (
        <DataTable id="platform-signups" rows={signups.data} onRowClick={setOpenSignup} columns={[
          { key: "company", label: "Company" }, { key: "contact_name", label: "Contact" }, { key: "email", label: "E-mail" },
          { key: "plan", label: "Plan", type: "label" }, { key: "seats", label: "Seats", type: "number" },
          { key: "flag", label: "Flag", hideSm: true }, { key: "created_at", label: "Received", type: "date" },
          { key: "status", label: "Status", type: "status", filter: true },
        ]} />
      )}
      {creating && (
        <Modal title="Create a workspace" onClose={() => setCreating(false)}>
          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            const v: any = formValues(e.currentTarget);
            v.trial = v.trial === "yes";
            if (await run(() => api("/platform/tenants", { body: v }), "Workspace created — the admin has an invitation")) { setCreating(false); reloadAll(); }
          }}>
            <div className="fields">
              <Field label="Company name" name="name" required full />
              <Field label="Admin e-mail" name="admin_email" type="email" required />
              <Field label="Admin name" name="admin_name" />
              <Field label="Plan" name="plan" as="select" options={["starter", "growth", "enterprise"]} defaultValue="growth" />
              <Field label="30-day trial" name="trial" as="select" options={[["yes", "Yes"], ["no", "No — bill now"]]} />
              <Field label="State" name="state" maxLength={2} />
              <Field label="EIN" name="ein" />
            </div>
            <button className="btn pri mt" disabled={busy}>Create and invite admin</button>
          </form>
        </Modal>
      )}
      <Drawer open={!!openTenant} onClose={() => setOpenTenant(null)} title={openTenant?.name ?? ""}>
        {openTenant && (
          <>
            <dl className="dl">
              <dt>Status</dt><dd><Chip status={openTenant.status} /></dd><dt>Plan</dt><dd>{label(openTenant.plan)} · {money(openTenant.price_per_user)}/user/month</dd>
              <dt>Trial ends</dt><dd>{date(openTenant.trial_ends_on)}</dd><dt>Live since</dt><dd>{date(openTenant.live_on)}</dd>
              <dt>Users</dt><dd>{openTenant.active_users} active · {openTenant.invited_users} invited</dd><dt>MRR</dt><dd>{money(openTenant.mrr)}</dd>
            </dl>
            <form className="form" onSubmit={async (e) => {
              e.preventDefault();
              if (await run(() => api(`/platform/tenants/${openTenant.id}`, { method: "PATCH", body: formValues(e.currentTarget) }), "Saved")) { setOpenTenant(null); reloadAll(); }
            }}>
              <Field label="Plan" name="plan" as="select" defaultValue={openTenant.plan} options={["starter", "growth", "enterprise"]} />
              <Field label="Status" name="status" as="select" defaultValue={openTenant.status} options={[["onboarding", "Onboarding"], ["active", "Active"], ["suspended", "Suspended (no sign-in)"], ["closed", "Closed"]]} />
              <Field label="Trial ends" name="trial_ends_on" type="date" defaultValue={openTenant.trial_ends_on ?? ""} />
              <button className="btn pri mt" disabled={busy}>Save</button>
            </form>
          </>
        )}
      </Drawer>
      <Drawer open={!!openSignup} onClose={() => setOpenSignup(null)} title={openSignup?.company ?? ""}>
        {openSignup && (
          <>
            <dl className="dl">
              <dt>Contact</dt><dd>{openSignup.contact_name} · {openSignup.email} · {openSignup.phone ?? ""}</dd><dt>State / EIN</dt><dd>{openSignup.state ?? "–"} · {openSignup.ein ?? "–"}</dd>
              <dt>Plan</dt><dd>{label(openSignup.plan)} · {openSignup.seats} seats</dd><dt>Checks</dt><dd>{openSignup.flag ?? "No flags"}</dd><dt>From IP</dt><dd>{openSignup.checks?.submitted_ip ?? "–"}</dd>
            </dl>
            {["pending", "needs_info"].includes(openSignup.status) && (
              <div className="row">
                <button className="btn pri" disabled={busy} onClick={async () => { if (await run(() => api(`/platform/signups/${openSignup.id}/decision`, { body: { decision: "approved" } }), "Approved — workspace created")) { setOpenSignup(null); reloadAll(); } }}>Approve & create workspace</button>
                <button className="btn" disabled={busy} onClick={async () => { const note = prompt("What do you need from them?"); if (note && await run(() => api(`/platform/signups/${openSignup.id}/decision`, { body: { decision: "needs_info", note } }), "Asked for more information")) { setOpenSignup(null); reloadAll(); } }}>Ask for more</button>
                <button className="btn" disabled={busy} onClick={async () => { const note = prompt("Reason (sent to the company):"); if (note && await run(() => api(`/platform/signups/${openSignup.id}/decision`, { body: { decision: "rejected", note } }), "Rejected")) { setOpenSignup(null); reloadAll(); } }}>Reject</button>
              </div>
            )}
          </>
        )}
      </Drawer>
    </>
  );
}
