"use client";

import { useState } from "react";
import { DataTable } from "@/components/DataTable";
import { ErrorBox, Field, Loading, Modal, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { label } from "@/lib/format";
import { isOwner, useSession, type Level } from "@/lib/session";
import { useApi } from "@/lib/useApi";

const BASE_ROLES: [string, string][] = [
  ["finance", "Finance"], ["account_manager", "Account manager"], ["legal", "Legal"], ["hr", "HR"],
  ["approver", "Approver"], ["viewer", "Viewer"], ["tenant_admin", "Admin"],
  ["vendor_admin", "Vendor login"], ["client_user", "Client login"], ["consultant", "Consultant login"],
];
const LEVELS: [Level, string][] = [["none", "Hidden"], ["read", "View"], ["write", "Edit"]];

/** Owner only: build custom roles — per module hidden / view / edit — and give them to people on Users & roles. */
export default function Roles() {
  const { workspace } = useSession();
  const owner = isOwner(workspace);
  const { data, error, loading, reload } = useApi<any>(owner ? "/roles" : null);
  const [editing, setEditing] = useState<any>(null);

  if (!owner) return (
    <>
      <PageHead title="Roles & permissions" />
      <p className="muted">Only the company owner can change roles and permissions.</p>
    </>
  );
  if (loading) return <Loading rows={5} />;
  return (
    <>
      <PageHead title="Roles & permissions"
        sub="Build roles like “Finance — view only” and give them to people on Users & roles. A role can only narrow what its base role allows."
        actions={<button className="btn pri" onClick={() => setEditing({ name: "", base_role: "finance", permissions: {} })}>New role</button>} />
      <ErrorBox error={error} retry={reload} />
      {data && (data.roles.length ? (
        <DataTable id="custom-roles" rows={data.roles} onRowClick={setEditing} columns={[
          { key: "name", label: "Role" }, { key: "base_role", label: "Based on", type: "label" },
          { key: "permissions", label: "Limits", value: (r) => Object.entries(r.permissions ?? {})
              .filter(([, v]) => v !== "write")
              .map(([k, v]) => `${data.modules.find((m: any) => m.key === k)?.label ?? label(k)}: ${v === "read" ? "view only" : "hidden"}`)
              .join(", ") || "None" },
          { key: "members", label: "People", type: "number" },
        ]} />
      ) : <p className="muted">No custom roles yet. Everyone has the full access of their base role.</p>)}
      {editing && data && <RoleEditor role={editing} modules={data.modules} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />}
    </>
  );
}

function RoleEditor({ role, modules, onClose, onSaved }: { role: any; modules: { key: string; label: string }[]; onClose: () => void; onSaved: () => void }) {
  const { run, busy } = useAction();
  const [name, setName] = useState<string>(role.name);
  const [base, setBase] = useState<string>(role.base_role);
  const [perms, setPerms] = useState<Record<string, Level>>(role.permissions ?? {});
  const isNew = !role.id;
  const save = async () => {
    const body = isNew ? { name, base_role: base, permissions: perms } : { name, permissions: perms };
    if (await run(() => api(isNew ? "/roles" : `/roles/${role.id}`, { method: isNew ? "POST" : "PATCH", body }), "Role saved")) onSaved();
  };
  return (
    <Modal title={isNew ? "New role" : role.name} onClose={onClose}>
      <div className="form">
        <Field label="Role name" name="name" value={name} onChange={(e: any) => setName(e.target.value)} required />
        <Field label="Based on" name="base_role" as="select" value={base} onChange={(e: any) => setBase(e.target.value)} options={BASE_ROLES} disabled={!isNew} />
        <div className="perm-grid">
          {modules.map((m) => (
            <div key={m.key} className="row" style={{ justifyContent: "space-between" }} role="radiogroup" aria-label={m.label}>
              <span>{m.label}</span>
              <span className="row" style={{ gap: 10 }}>
                {LEVELS.map(([v, l]) => (
                  <label key={v} style={{ display: "flex", gap: 4, alignItems: "center" }}>
                    <input type="radio" name={`p-${m.key}`} checked={(perms[m.key] ?? "write") === v}
                      onChange={() => setPerms({ ...perms, [m.key]: v })} />{l}
                  </label>
                ))}
              </span>
            </div>
          ))}
        </div>
        <div className="row mt">
          <button className="btn pri" disabled={busy || name.trim().length < 2} onClick={save}>Save role</button>
          {!isNew && <button className="btn" disabled={busy} onClick={async () => {
            if (await run(() => api(`/roles/${role.id}`, { method: "DELETE" }), "Role deleted — its people keep their base role")) onSaved();
          }}>Delete role</button>}
        </div>
      </div>
    </Modal>
  );
}
