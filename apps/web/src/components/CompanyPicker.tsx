"use client";

import { useState } from "react";
import { useApi } from "@/lib/useApi";
import { roleList } from "@/lib/format";

/** Company autocomplete: type a few letters to get suggestions from the company
 * directory (every signed-in tenant member can search it), then pick one. */
export function CompanyPicker({ name = "company_id", label = "Company", value, defaultValue, onChange, excludeId, required, autoFocus }: {
  name?: string; label?: string; value?: string; defaultValue?: string; onChange?: (e: any) => void; excludeId?: string; required?: boolean; autoFocus?: boolean;
}) {
  const { data, error, loading } = useApi<any[]>("/companies/directory");
  const [q, setQ] = useState("");
  const [internal, setInternal] = useState(defaultValue ?? "");
  const [open, setOpen] = useState(false);
  const shown = value !== undefined ? value : internal;
  const selected = (data ?? []).find((c) => c.id === shown);
  const needle = q.trim().toLowerCase();
  const suggestions = (data ?? [])
    .filter((c) => (!excludeId || c.id !== excludeId) &&
      (!needle || `${c.name} ${c.business_code ?? ""}`.toLowerCase().includes(needle)))
    .slice(0, 8);
  const pick = (id: string) => {
    setInternal(id);
    onChange?.({ target: { value: id } });
    setOpen(false);
    setQ("");
  };
  const clear = () => {
    setInternal("");
    onChange?.({ target: { value: "" } });
    setQ("");
  };
  // Typing the full name and tabbing out picks the exact match.
  const blur = () => {
    setOpen(false);
    if (!shown && needle) {
      const exact = (data ?? []).find((c) =>
        (!excludeId || c.id !== excludeId) && c.name.toLowerCase() === needle);
      if (exact) pick(exact.id);
    }
  };
  return (
    <div style={{ gridColumn: "1 / -1" }}>
      <label htmlFor="co-search">{label}</label>
      <div className="suggest">
        <input id="co-search" className="ctl" value={selected ? selected.name : q}
          placeholder={loading ? "Loading companies…" : "Type a few letters…"}
          autoFocus={autoFocus} required={required && !shown} readOnly={!!selected}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => !selected && setOpen(true)} onBlur={blur} style={{ width: "100%" }} />
        <input type="hidden" name={name} value={shown} />
        {!selected && open && !loading && !error && !!needle && (
          <div className="suggest-list" role="listbox" onMouseDown={(e) => e.preventDefault()}>
            {suggestions.map((c) => (
              <button key={c.id} type="button" role="option" aria-selected="false"
                      className="suggest-item" onClick={() => pick(c.id)}>
                <b>{c.name}</b>{c.business_code ? ` · ${c.business_code}` : ""}{" "}
                <span className="muted">({roleList(c)})</span>
              </button>
            ))}
            {!suggestions.length && <p className="note" style={{ padding: "8px 10px" }}>No companies match “{q}”. Clear the search or check the spelling.</p>}
          </div>
        )}
      </div>
      {selected
        ? <p className="note">{selected.business_code ? `${selected.business_code} · ` : ""}{roleList(selected)} · <button type="button" className="btn sm" onClick={clear}>Change</button></p>
        : <p className="note">{loading ? "Loading the company directory…" : error ? `Couldn't load the company directory: ${error.message}` : "Pick the counterparty from the suggestions."}</p>}
    </div>
  );
}
