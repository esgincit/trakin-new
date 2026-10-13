"use client";

import { useState } from "react";
import { DataTable } from "@/components/DataTable";
import { Drawer, ErrorBox, PageHead } from "@/components/ui";
import { download } from "@/lib/api";
import { dateTime, label } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function Audit() {
  const [filters, setFilters] = useState<{ entity?: string; since?: string; until?: string; q?: string }>({});
  const { data, error, reload } = useApi<any[]>("/audit", { ...filters, limit: 500 });
  const [open, setOpen] = useState<any>(null);
  return (
    <>
      <PageHead title="Audit log" sub="Every create, change and delete — who, when, from which IP address, and exactly what changed. It can't be edited."
        actions={<button className="btn" onClick={() => download("/data/export/audit.csv", `mytrakin-audit-${new Date().toISOString().slice(0, 10)}.csv`)}>Export CSV</button>} />
      <form className="toolbar" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); setFilters(Object.fromEntries([...f.entries()].filter(([, v]) => v)) as any); }}>
        <select name="entity" className="ctl" aria-label="Record type" defaultValue="">
          <option value="">All records</option>
          {["invoices", "payments", "placements", "timesheets", "agreements", "sows", "companies", "consultants", "memberships", "envelopes", "documents", "tracked_documents", "policies", "tenants"].map((e) => <option key={e} value={e}>{label(e)}</option>)}
        </select>
        <input name="since" type="date" className="ctl" aria-label="From" />
        <input name="until" type="date" className="ctl" aria-label="To" />
        <input name="q" className="ctl" placeholder="Person or value" />
        <button className="btn">Search</button>
      </form>
      <ErrorBox error={error} retry={reload} />
      <DataTable id="audit" rows={data} onRowClick={setOpen} columns={[
        { key: "at", label: "When", render: (r) => dateTime(r.at), value: (r) => r.at },
        { key: "actor", label: "Who", filter: true }, { key: "actor_role", label: "Role", type: "label", hideSm: true },
        { key: "action", label: "Action", type: "label", filter: true }, { key: "entity", label: "Record", type: "label", filter: true },
        { key: "fields", label: "Changed", value: (r) => (r.action === "update" ? Object.keys(r.changes ?? {}).join(", ") : ""), hideSm: true },
        { key: "ip", label: "IP address", hideSm: true },
      ]} />
      <Drawer open={!!open} onClose={() => setOpen(null)} title={open ? `${label(open.action)} ${label(open.entity)}` : ""}>
        {open && (
          <>
            <dl className="dl"><dt>When</dt><dd>{dateTime(open.at)}</dd><dt>Who</dt><dd>{open.actor} ({label(open.actor_role)})</dd><dt>IP address</dt><dd>{open.ip ?? "–"}</dd><dt>Device</dt><dd style={{ overflowWrap: "anywhere" }}>{open.user_agent ?? "–"}</dd><dt>Record id</dt><dd><code>{open.entity_id}</code></dd></dl>
            {open.action === "update" ? (
              <table><thead><tr><th>Field</th><th>Before</th><th>After</th></tr></thead>
                <tbody>{Object.entries(open.changes ?? {}).map(([k, v]: any) => <tr key={k}><td>{k}</td><td style={{ whiteSpace: "normal" }}>{JSON.stringify(v.from)}</td><td style={{ whiteSpace: "normal" }}>{JSON.stringify(v.to)}</td></tr>)}</tbody></table>
            ) : <pre style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{JSON.stringify(open.changes, null, 2)}</pre>}
          </>
        )}
      </Drawer>
    </>
  );
}
