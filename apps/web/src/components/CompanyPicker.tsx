"use client";

import { useState } from "react";
import { useApi } from "@/lib/useApi";
import { roleList } from "@/lib/format";

/** Searchable company picker: type to filter, then choose. Reads from the
 * company directory, which every signed-in tenant member can search. */
export function CompanyPicker({ name = "company_id", label = "Company", value, defaultValue, onChange, excludeId, required, autoFocus }: {
  name?: string; label?: string; value?: string; defaultValue?: string; onChange?: (e: any) => void; excludeId?: string; required?: boolean; autoFocus?: boolean;
}) {
  const { data } = useApi<any[]>("/companies/directory");
  const [q, setQ] = useState("");
  const [internal, setInternal] = useState(defaultValue ?? "");
  const shown = value !== undefined ? value : internal;
  const pick = (e: any) => { setInternal(e.target.value); onChange?.(e); };
  const needle = q.trim().toLowerCase();
  const rows = (data ?? []).filter((c) =>
    (!excludeId || c.id !== excludeId) &&
    (!needle || `${c.name} ${c.business_code ?? ""}`.toLowerCase().includes(needle)));
  return (
    <>
      <div style={{ gridColumn: "1 / -1" }}>
        <label htmlFor="co-search">Find company</label>
        <input id="co-search" className="ctl" value={q} placeholder="Type to filter the list…" onChange={(e) => setQ(e.target.value)} style={{ width: "100%" }} />
      </div>
      <div style={{ gridColumn: "1 / -1" }}>
        <label htmlFor="co-pick">{label}</label>
        <select id="co-pick" name={name} className="ctl" required={required} value={shown} onChange={pick} autoFocus={autoFocus} style={{ width: "100%" }}>
          <option value="">Choose…</option>
          {rows.map((c) => <option key={c.id} value={c.id}>{c.name}{c.business_code ? ` · ${c.business_code}` : ""} ({roleList(c)})</option>)}
        </select>
        {!rows.length && <p className="note">No companies match “{q}”. Clear the search or check the spelling.</p>}
      </div>
    </>
  );
}
