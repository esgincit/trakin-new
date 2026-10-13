"use client";

import { useState } from "react";
import { DataButtons } from "@/components/DataButtons";
import { DataTable } from "@/components/DataTable";
import { Avatar, Drawer, ErrorBox, Field, formValues, Modal, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime, label } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const ROLES: [string, string][] = [
  ["tenant_admin", "Admin — everything, including users and settings"], ["finance", "Finance — invoices, payments, rates"],
  ["account_manager", "Account manager — clients, projects, placements, AR"], ["legal", "Legal — contracts, e-signatures, audit"],
  ["hr", "HR — onboarding, compliance, policies"], ["approver", "Approver — timesheets"], ["viewer", "Viewer — read only"],
  ["vendor_admin", "Vendor — their own consultants and AP invoices"], ["client_user", "Client — their invoices and projects"], ["consultant", "Consultant — self-service"],
];

export default function Users() {
  const { data, error, reload } = useApi<any[]>("/users");
  const companies = useApi<any[]>("/companies");
  const consultants = useApi<any[]>("/consultants");
  const [inviting, setInviting] = useState(false);
  const [createdLogin, setCreatedLogin] = useState<string | null>(null);
  const [editing, setEditing] = useState<any>(null);
  const [role, setRole] = useState("viewer");
  const { run, busy } = useAction();

  return (
    <>
      <PageHead title="Users & roles" sub="Who can sign in, what they can see, and who reports to whom. Every change is in the audit log."
        actions={<button className="btn pri" onClick={() => setInviting(true)}>Invite user</button>} />
      <ErrorBox error={error} retry={reload} />
      <DataTable id="users" rows={data} onRowClick={setEditing} cardTitle={(r) => <span className="row"><Avatar name={r.full_name ?? r.email} />{r.full_name ?? r.email}</span>} columns={[
        { key: "user_code", label: "ID", value: (r) => r.user_code ?? "—" },
        { key: "full_name", label: "Name", value: (r) => r.full_name ?? "(invited)" }, { key: "email", label: "E-mail" },
        { key: "role", label: "Role", type: "label", filter: true }, { key: "title", label: "Title", hideSm: true },
        { key: "manager", label: "Reports to", hideSm: true }, { key: "company", label: "Company", value: (r) => r.company ?? r.consultant, hideSm: true },
        { key: "last_active_at", label: "Last active", render: (r) => dateTime(r.last_active_at), value: (r) => r.last_active_at },
        { key: "status", label: "Status", type: "status", filter: true },
      ]} toolbar={<DataButtons entity="users" label="users" />} />
      {inviting && (
        <Modal title="Invite a user" onClose={() => { setInviting(false); setCreatedLogin(null); }}>
          {createdLogin ? (
            <>
              <p className="muted">Their password login is ready. Share this once — it won't be shown again.
                They sign in with their e-mail, choose “Use a password”, then change it under Account &amp; security.</p>
              <p style={{ fontSize: 20, letterSpacing: 1 }}><code>{createdLogin}</code></p>
              <button className="btn pri mt" style={{ width: "100%" }} onClick={() => { setInviting(false); setCreatedLogin(null); reload(); }}>Done</button>
            </>
          ) : (
          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            const v: any = formValues(e.currentTarget);
            if (v.signing_limit) v.signing_limit = Number(v.signing_limit);
            const res = await run(() => api<any>("/users", { body: { ...v, role, create_login: v.create_login === "on" } }), "Invitation sent");
            if (res?.temp_password) setCreatedLogin(res.temp_password);
            else if (res) { setInviting(false); reload(); }
          }}>
            <Field label="E-mail" name="email" type="email" required />
            <Field label="Role" name="role_pick" as="select" value={role} onChange={(e: any) => setRole(e.target.value)} options={ROLES} />
            {["vendor_admin", "client_user"].includes(role) && <Field label="Company" name="company_id" as="select" required options={[["", "Choose…"], ...(companies.data ?? []).map((c) => [c.id, c.name] as [string, string])]} />}
            {role === "consultant" && <Field label="Consultant record" name="consultant_id" as="select" required options={[["", "Choose…"], ...(consultants.data ?? []).map((c) => [c.id, c.full_name] as [string, string])]} />}
            <div className="fields">
              <Field label="Title" name="title" />
              <Field label="Reports to" name="manager_id" as="select" options={[["", "–"], ...(data ?? []).filter((u) => u.user_id).map((u) => [u.id, u.full_name ?? u.email] as [string, string])]} />
              {["tenant_admin", "finance", "account_manager"].includes(role) && <Field label="Approval limit ($)" name="signing_limit" type="number" min="0" />}
            </div>
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}><input type="checkbox" name="create_login" style={{ marginTop: 4 }} />
              <span>Also create their password login now <span className="muted">(no e-mail needed — use while e-mail codes are unavailable)</span></span></label>
            <p className="note">They sign in with this e-mail (one-time code, SSO, Google or Microsoft). Admin and finance roles must set up two-step verification.</p>
            <button className="btn pri mt" disabled={busy}>Send invitation</button>
          </form>
          )}
        </Modal>
      )}
      <Drawer open={!!editing} onClose={() => setEditing(null)} title={editing?.full_name ?? editing?.email ?? ""}>
        {editing && (
          <form className="form" onSubmit={async (e) => {
            e.preventDefault();
            const v: any = formValues(e.currentTarget);
            if (v.signing_limit) v.signing_limit = Number(v.signing_limit);
            if (await run(() => api(`/users/${editing.id}`, { method: "PATCH", body: v }), "Saved")) { setEditing(null); reload(); }
          }}>
            <p className="muted">{editing.email} · {label(editing.status)}</p>
            <Field label="Role" name="role" as="select" defaultValue={editing.role} options={ROLES} />
            <Field label="Title" name="title" defaultValue={editing.title ?? ""} />
            <Field label="Reports to" name="manager_id" as="select" defaultValue={editing.manager_id ?? ""} options={[["", "–"], ...(data ?? []).filter((u) => u.user_id && u.id !== editing.id).map((u) => [u.id, u.full_name ?? u.email] as [string, string])]} />
            <Field label="Approval limit ($)" name="signing_limit" type="number" defaultValue={editing.signing_limit ?? ""} />
            <Field label="Access" name="status" as="select" defaultValue={editing.status === "invited" ? "active" : editing.status} options={[["active", "Active"], ["locked", "Locked (temporarily)"], ["deactivated", "Deactivated"]]} />
            <div className="row mt">
              <button className="btn pri" disabled={busy}>Save</button>
              {editing.status === "invited" && <button type="button" className="btn" disabled={busy} onClick={async () => { if (await run(() => api(`/users/${editing.id}`, { method: "DELETE" }), "Invitation withdrawn")) { setEditing(null); reload(); } }}>Withdraw invitation</button>}
            </div>
          </form>
        )}
      </Drawer>
    </>
  );
}
