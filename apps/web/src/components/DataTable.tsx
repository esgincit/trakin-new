"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { date, label, money, num } from "@/lib/format";
import { iso } from "@/lib/weeks";
import { Chip, Empty } from "./ui";

export type Column<T> = {
  key: string;
  label: string;
  /** How to show the value. Defaults by `type`. */
  render?: (row: T) => ReactNode;
  /** text (default) | money | number | date | status | label */
  type?: "text" | "money" | "number" | "date" | "status" | "label";
  /** Offer a dropdown filter with this column's distinct values. */
  filter?: boolean;
  /** Hidden on phones. */
  hideSm?: boolean;
  /** Value used for search, sort, filter and CSV (defaults to row[key]). */
  value?: (row: T) => string | number | null | undefined;
};

type Props<T> = {
  rows: T[] | undefined;
  columns: Column<T>[];
  /** Used for remembering the list/cards choice and for the CSV file name. */
  id: string;
  onRowClick?: (row: T) => void;
  /** Title shown on cards (defaults to the first column). */
  cardTitle?: (row: T) => ReactNode;
  cardAside?: (row: T) => ReactNode;
  toolbar?: ReactNode;
  empty?: ReactNode;
  pageSize?: number;
};

function raw<T>(row: T, col: Column<T>): any {
  return col.value ? col.value(row) : (row as any)[col.key];
}

function show<T>(row: T, col: Column<T>): ReactNode {
  if (col.render) return col.render(row);
  const v = raw(row, col);
  switch (col.type) {
    case "money": return money(v);
    case "number": return num(v);
    case "date": return date(v);
    case "status": return v ? <Chip status={v} /> : "–";
    case "label": return label(v);
    default: return v ?? "–";
  }
}

function text<T>(row: T, col: Column<T>): string {
  const v = raw(row, col);
  if (v === null || v === undefined) return "";
  if (col.type === "label" || col.type === "status") return label(String(v));
  return String(v);
}

/** Search box, column filters, sorting, list/cards views, paging and CSV of what you see. */
export function DataTable<T>({ rows, columns, id, onRowClick, cardTitle, cardAside, toolbar, empty, pageSize = 50 }: Props<T>) {
  const [q, setQ] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const [view, setView] = useState<"list" | "cards">("list");
  const [page, setPage] = useState(1);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(`mytrakin.view.${id}`);
      if (saved === "cards" || saved === "list") setView(saved);
    } catch { /* storage unavailable: default to list */ }
  }, [id]);

  const chooseView = (v: "list" | "cards") => {
    setView(v);
    try { localStorage.setItem(`mytrakin.view.${id}`, v); } catch { /* ignore */ }
  };

  const filterable = columns.filter((c) => c.filter);
  const options = useMemo(() => {
    const out: Record<string, string[]> = {};
    for (const col of filterable) {
      out[col.key] = [...new Set((rows ?? []).map((r) => text(r, col)).filter(Boolean))].sort();
    }
    return out;
  }, [rows, filterable]);

  const visible = useMemo(() => {
    let list = rows ?? [];
    const needle = q.trim().toLowerCase();
    if (needle) list = list.filter((r) => columns.some((c) => text(r, c).toLowerCase().includes(needle)));
    for (const [k, v] of Object.entries(filters)) {
      if (!v) continue;
      const col = columns.find((c) => c.key === k)!;
      list = list.filter((r) => text(r, col) === v);
    }
    if (sort) {
      const col = columns.find((c) => c.key === sort.key)!;
      const numeric = col.type === "money" || col.type === "number";
      list = [...list].sort((a, b) => {
        const x = raw(a, col), y = raw(b, col);
        if (x === y) return 0;
        if (x === null || x === undefined) return 1;
        if (y === null || y === undefined) return -1;
        return (numeric ? Number(x) - Number(y) : String(x).localeCompare(String(y))) * sort.dir;
      });
    }
    return list;
  }, [rows, q, filters, sort, columns]);

  useEffect(() => setPage(1), [q, filters, sort]);
  const shown = visible.slice(0, page * pageSize);

  const toggleSort = (key: string) =>
    setSort((s) => (s?.key !== key ? { key, dir: 1 } : s.dir === 1 ? { key, dir: -1 } : null));

  const exportCsv = () => {
    const esc = (raw: string) => {
      // Neutralise spreadsheet formulas (CSV injection), but leave negative numbers alone.
      const s = /^[=+\-@\t\r]/.test(raw) && Number.isNaN(Number(raw)) ? `'${raw}` : raw;
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const lines = [columns.map((c) => esc(c.label)), ...visible.map((r) => columns.map((c) => esc(text(r, c))))];
    const blob = new Blob(["﻿" + lines.map((l) => l.join(",")).join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `mytrakin-${id}-${iso(new Date())}.csv`;
    a.click();
  };

  return (
    <div>
      <div className="toolbar">
        <input className="ctl" type="search" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)}
               aria-label="Search this list" style={{ minWidth: 200 }} />
        {filterable.map((col) => (
          <select key={col.key} className="ctl" value={filters[col.key] ?? ""} aria-label={`Filter by ${col.label}`}
                  onChange={(e) => setFilters((f) => ({ ...f, [col.key]: e.target.value }))}>
            <option value="">{col.label}: all</option>
            {options[col.key]?.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        ))}
        {(q || Object.values(filters).some(Boolean)) && (
          <button className="btn sm" onClick={() => { setQ(""); setFilters({}); }}>Clear</button>
        )}
        <span className="grow" />
        {toolbar}
        <span className="muted" style={{ fontSize: 12.5 }}>{visible.length} of {rows?.length ?? 0}</span>
        <div className="seg" role="group" aria-label="View">
          <button className={view === "list" ? "on" : ""} onClick={() => chooseView("list")} aria-pressed={view === "list"}>List</button>
          <button className={view === "cards" ? "on" : ""} onClick={() => chooseView("cards")} aria-pressed={view === "cards"}>Cards</button>
        </div>
        <button className="btn sm" onClick={exportCsv} title="Download what you see as CSV">Export</button>
      </div>

      {rows && visible.length === 0 ? (
        <div className="card"><Empty>{rows.length ? "Nothing matches your search or filters." : empty ?? "Nothing here yet."}</Empty></div>
      ) : view === "list" ? (
        <div className="tw">
          <table>
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c.key} className={`sortable ${c.type === "money" || c.type === "number" ? "num" : ""} ${c.hideSm ? "hide-sm" : ""}`}
                      onClick={() => toggleSort(c.key)} aria-sort={sort?.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
                    {c.label} <span className="sarr">{sort?.key === c.key ? (sort.dir === 1 ? "▲" : "▼") : ""}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((r, i) => (
                <tr key={`${(r as any).id ?? ""}:${i}`} className={onRowClick ? "click" : ""} onClick={() => onRowClick?.(r)}
                    tabIndex={onRowClick ? 0 : undefined} onKeyDown={(e) => e.key === "Enter" && onRowClick?.(r)}>
                  {columns.map((c) => (
                    <td key={c.key} className={`${c.type === "money" || c.type === "number" ? "num" : ""} ${c.hideSm ? "hide-sm" : ""}`}>
                      {show(r, c)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="cgrid">
          {shown.map((r, i) => (
            <div key={`${(r as any).id ?? ""}:${i}`} className={`ccard ${onRowClick ? "click" : ""}`} onClick={() => onRowClick?.(r)}
                 tabIndex={onRowClick ? 0 : undefined} onKeyDown={(e) => e.key === "Enter" && onRowClick?.(r)}>
              <div className="ch">
                <b style={{ flex: 1, minWidth: 0 }}>{cardTitle ? cardTitle(r) : show(r, columns[0]!)}</b>
                {cardAside?.(r)}
              </div>
              <dl>
                {columns.slice(cardTitle ? 0 : 1).map((c) => (
                  <div key={c.key} style={{ display: "contents" }}>
                    <dt>{c.label}</dt>
                    <dd>{show(r, c)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      )}
      {visible.length > shown.length && (
        <div className="row mt" style={{ justifyContent: "center" }}>
          <button className="btn" onClick={() => setPage((p) => p + 1)}>Show more ({visible.length - shown.length} left)</button>
        </div>
      )}
      {!rows && <div className="card"><div className="skel" /><div className="skel mt" /><div className="skel mt" /></div>}
    </div>
  );
}
