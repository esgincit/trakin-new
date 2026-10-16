"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Chip, ErrorBox, PageHead, useAction } from "@/components/ui";
import { api, download } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { iso } from "@/lib/weeks";

const EXPORTS: [string, string][] = [
  ["companies", "Clients & vendors"], ["consultants", "Consultants (incl. former)"], ["projects", "Projects"], ["placements", "Placements & rates"],
  ["agreements", "Agreements"], ["sows", "SOWs"], ["ar_invoices", "Client invoices (AR)"], ["ap_invoices", "Vendor invoices (AP)"],
  ["payments", "Payments"], ["payroll", "W-2 payroll"], ["timesheets", "Timesheets"], ["tracked_documents", "Expiring documents"], ["audit", "Audit log"],
];

export default function DataPage() {
  return <Suspense><Data /></Suspense>;
}

function Data() {
  const params = useSearchParams();
  const templates = useApi<any[]>("/data/templates");
  const jobs = useApi<any[]>("/data/import-jobs");
  const [entity, setEntity] = useState(params.get("entity") ?? "companies");
  const [file, setFile] = useState<File | null>(null);
  const [check, setCheck] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  const { run, busy } = useAction();
  const template = templates.data?.find((t) => t.key === entity);
  const day = iso(new Date());

  const send = async (dryRun: boolean) => {
    if (!file) return;
    const form = new FormData();
    form.set("file", file);
    const r = await run(() => api(`/data/import/${entity}`, { form, query: { dry_run: dryRun } }), dryRun ? undefined : "Import finished");
    if (!r) return;
    if (dryRun) { setCheck(r); setResult(null); } else { setResult(r); setCheck(null); jobs.reload(); }
  };

  return (
    <>
      <PageHead title="Import & export" sub="Bring in existing clients, vendors (active and inactive), consultants (current and former), MSAs, SOWs, rates and invoice history. Export anything as CSV." />
      <ErrorBox error={templates.error} />
      <div className="grid c2">
        <div className="card">
          <h3>Import</h3>
          <ol className="muted" style={{ paddingLeft: 18, marginTop: 0 }}>
            <li>Pick what you're importing and download the template (it has sample rows).</li>
            <li>Fill it in Excel or Google Sheets and save as CSV.</li>
            <li>Check the file — nothing is saved until you import. Re-importing updates rows instead of duplicating them.</li>
          </ol>
          <div className="row">
            <select className="ctl" value={entity} onChange={(e) => { setEntity(e.target.value); setCheck(null); setResult(null); }} aria-label="What to import">
              {templates.data?.map((t) => <option key={t.key} value={t.key} disabled={!t.can_import}>{t.label}{t.can_import ? "" : " (not your role)"}</option>)}
            </select>
            <button className="btn sm" onClick={() => download(`/data/templates/${entity}.csv`, `mytrakin-${entity}-template.csv`)}>Download template</button>
          </div>
          {template && (
            <p className="note">Columns: {template.columns.map((c: any) => (c.required ? <b key={c.name}>{c.name}* </b> : <span key={c.name}>{c.name} </span>))}
              <br />* required. Dates as YYYY-MM-DD.</p>
          )}
          <input type="file" accept=".csv,text/csv" className="ctl mt" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setCheck(null); setResult(null); }} />
          <div className="row mt">
            <button className="btn" disabled={!file || busy} onClick={() => send(true)}>Check file</button>
            <button className="btn pri" disabled={!file || busy || !check || check.valid === 0} onClick={() => send(false)}>Import {check ? `${check.valid} row(s)` : ""}</button>
          </div>
          {check && (
            <div className="mt">
              <p><Chip status={check.errors.length ? "pending" : "ok"}>{check.valid} of {check.rows} rows ready</Chip>{check.ignored_columns.length > 0 && <span className="muted"> · ignored columns: {check.ignored_columns.join(", ")}</span>}</p>
              {check.errors.slice(0, 50).map((e: any) => <div key={e.line} className="err">Line {e.line}: {e.errors.join("; ")}</div>)}
            </div>
          )}
          {result && (
            <div className="mt">
              <p className="ok">{result.created} created, {result.updated} updated{result.errors.length ? `, ${result.errors.length} skipped` : ""}.</p>
              {result.errors.slice(0, 50).map((e: any) => <div key={e.line} className="err">Line {e.line}: {e.errors.join("; ")}</div>)}
            </div>
          )}
        </div>
        <div className="card">
          <h3>Export</h3>
          <p className="muted">Exports use the same columns as the templates, so you can edit and re-import.</p>
          {EXPORTS.map(([key, lbl]) => (
            <div key={key} className="alert">
              <div style={{ flex: 1 }}>{lbl}</div>
              <button className="btn sm" onClick={() => run(() => download(`/data/export/${key}.csv`, `mytrakin-${key}-${day}.csv`))}>CSV</button>
            </div>
          ))}
        </div>
      </div>
      <div className="card mt">
        <h3>Import history</h3>
        <table><thead><tr><th>When</th><th>What</th><th>File</th><th className="num">Rows</th><th className="num">Created</th><th className="num">Updated</th><th className="num">Errors</th><th>By</th></tr></thead>
          <tbody>{jobs.data?.map((j) => <tr key={j.id}><td>{dateTime(j.created_at)}</td><td>{j.entity}</td><td>{j.filename}</td><td className="num">{j.total_rows}</td><td className="num">{j.imported_rows}</td><td className="num">{j.updated_rows}</td><td className="num">{j.error_count}</td><td>{j.by}</td></tr>)}</tbody></table>
      </div>
    </>
  );
}
