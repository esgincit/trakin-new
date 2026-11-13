"use client";

import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import type { ApiError } from "@/lib/api";
import { label, tone } from "@/lib/format";

/** Jumps to Import & export with the entity pre-selected (template download included there). */
export function ImportButton({ entity, label: l = "Import" }: { entity: string; label?: string }) {
  return <Link className="btn" href={`/data?entity=${entity}`} aria-label={`Import ${label(entity)}`}>{l}</Link>;
}

export function Chip({ status, children }: { status?: string | null; children?: ReactNode }) {
  return <span className={`chip ${tone(status)}`}>{children ?? label(status)}</span>;
}

/* ---------------------------------------------------------------- sub-tab icons */

const stroke = {
  width: 15, height: 15, viewBox: "0 0 24 24", fill: "none",
  stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round",
} as const;

const P = (d: string) => <path d={d} />;

/** One icon per sub-tab across the app, keyed by the page's tab key. */
const TAB_ICONS: Record<string, ReactNode> = {
  // Invoices
  ar: <svg {...stroke}>{P("M4 4h13l3 3v13H4Z")}<path d="M12 8.5v7M9.8 10.7c0-1.2 1-1.9 2.2-1.9s2.2.7 2.2 1.7-1 1.6-2.2 1.9-2.2.9-2.2 1.9 1 1.7 2.2 1.7 2.2-.7 2.2-1.9" /></svg>,
  ap: <svg {...stroke}>{P("M4 4h16v16H4Z")}<path d="M12 8v8M9.5 10.5 12 8l2.5 2.5M9.5 13.5 12 16l2.5-2.5" /></svg>,
  credits: <svg {...stroke}>{P("M7 3h10a2 2 0 0 1 2 2v16l-3-2-2 2-2-2-2 2-2-2-3 2V5a2 2 0 0 1 2-2Z")}<path d="M9 8h6M9 12h4" /></svg>,
  // Payroll, 1099 & referrals
  payroll: <svg {...stroke}>{P("M3 7h18v12H3Z")}<circle cx="12" cy="13" r="2.6" /><path d="M7 7V5h10v2" /></svg>,
  "1099": <svg {...stroke}>{P("M5 3h11l4 4v14H5Z")}<path d="M9 12h6M9 16h4" /><path d="m15 16 2-2" /></svg>,
  referrals: <svg {...stroke}>{P("M6 9a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Zm12 11a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM6 9v4a4 4 0 0 0 4 4h8")}<circle cx="16.5" cy="17.5" r="0.5" /></svg>,
  expenses: <svg {...stroke}>{P("M3 6h18v13H3Z")}<path d="M3 10h18M7 15h4" /></svg>,
  time_off: <svg {...stroke}>{P("M4 5h16v15H4Z")}<path d="M4 9h16M9 3v4M15 3v4" /><path d="m9.5 14 1.7 1.7 3.3-3.3" /></svg>,
  // Compliance
  documents: <svg {...stroke}>{P("M6 3h9l4 4v14H6Z")}<circle cx="13" cy="13" r="4" /><path d="M13 11v2l1.3 1.3" /></svg>,
  work_auth: <svg {...stroke}>{P("M4 4h16v16H4Z")}<circle cx="9" cy="10" r="2" /><path d="M6 16c.5-2 1.7-2.8 3-2.8s2.5.8 3 2.8M14 8h4M14 11.5h4M14 15h3" /></svg>,
  policies: <svg {...stroke}>{P("M12 3 5 6v5.5c0 4.4 2.9 8 7 9.5 4.1-1.5 7-5.1 7-9.5V6Z")}<path d="m9.2 11.8 2 2 3.6-3.8" /></svg>,
  registrations: <svg {...stroke}>{P("M4 21V5l7-2v18M11 9l9 2v10")}<path d="M7 8h.01M7 12h.01M7 16h.01M15 14h.01M15 17h.01" /></svg>,
  reminders: <svg {...stroke}>{P("M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6Z")}<path d="M10 19a2 2 0 0 0 4 0" /></svg>,
  // Consultants
  onboarding: <svg {...stroke}>{P("M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z")}<path d="M2.5 20c.6-3.2 3-5 6.5-5M18 8v6M15 11h6" /></svg>,
  active: <svg {...stroke}>{P("M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z")}<path d="M2.5 20c.6-3.2 3-5 6.5-5s5.9 1.8 6.5 5" /><path d="m15 11.5 2 2 3.5-3.5" /></svg>,
  former: <svg {...stroke}>{P("M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z")}<path d="M2.5 20c.6-3.2 3-5 6.5-5s5.9 1.8 6.5 5" /><path d="m15 9.5 5 5M20 9.5l-5 5" /></svg>,
  all_people: <svg {...stroke}>{P("M8.5 11a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z")}<path d="M2.5 19c.6-3 2.8-4.7 6-4.7s5.4 1.7 6 4.7" /><path d="M16.5 8.5a2.6 2.6 0 1 0 0-5.2 2.6 2.6 0 0 0 0 5.2ZM18.6 12.4c2 .6 3.4 2 3.9 4.3" /></svg>,
  // MSAs & SOWs
  agreements: <svg {...stroke}>{P("M6 3h9l4 4v14H6Z")}<path d="M9 8h7M9 12h7M9 16h3" /><path d="M9 18.5 10.5 20l3-3" /></svg>,
  sows: <svg {...stroke}>{P("m12 3 9 4.5-9 4.5L3 7.5Z")}<path d="m3 12.5 9 4.5 9-4.5M3 16.5 12 21l9-4.5" /></svg>,
  missing: <svg {...stroke}>{P("m12 4 9.5 16h-19Z")}<path d="M12 10.5v4M12 17.2h.01" /></svg>,
  // Timesheets
  week: <svg {...stroke}>{P("M4 5h16v15H4Z")}<path d="M4 9h16M9 3v4M15 3v4" /><path d="m9 14 1.7 1.7L14 12.4" /></svg>,
  history: <svg {...stroke}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></svg>,
  // Platform
  overview: <svg {...stroke}>{P("M4 20V4")}<path d="M4 20h16M8 16v-5M12 16V8M16 16v-3" /></svg>,
  companies: <svg {...stroke}>{P("M4 21V8l8-3v16M12 21V12l8 2v7")}<path d="M7.5 10h.01M7.5 13h.01M7.5 16h.01M16 16h.01M16 18.5h.01" /></svg>,
  queue: <svg {...stroke}>{P("M4 5h16v6a8 8 0 0 1-16 0Z")}<path d="M9 19h6M12 11v-2" /></svg>,
  admins: <svg {...stroke}>{P("M10.5 3.5 5 6v5.2c0 4 2.3 7.3 5.5 8.8 3.2-1.5 5.5-4.8 5.5-8.8V6Z")}<circle cx="16.5" cy="16.5" r="3" /><path d="m18.8 18.8 2 2" /></svg>,
  // Projects & placements
  projects: <svg {...stroke}>{P("M4 7h5l2 2h9v11H4Z")}<path d="M4 7V5h5l2 2" /></svg>,
  placements: <svg {...stroke}>{P("M9 11a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z")}<path d="M3.5 19c.5-2.9 2.6-4.5 5.5-4.5 1.2 0 2.2.2 3.1.7" /><rect x="13.5" y="13.5" width="7" height="7" rx="1" /><path d="M15.5 13.5V12a1.5 1.5 0 0 1 3 0v1.5" /></svg>,
};

const TAB_ICONS_DEFAULT: ReactNode = <svg {...stroke}><circle cx="12" cy="12" r="8.5" /><path d="M12 8.5h.01M12 11.5V16" /></svg>;

/** Icon shown inside a module's sub-tab; falls back to a neutral marker for unknown keys. */
export function SubTabIcon({ tabKey, label }: { tabKey: string; label?: string }) {
  return (
    <span className="tab-ico" aria-hidden="true" title={label}>
      {TAB_ICONS[tabKey] ?? TAB_ICONS_DEFAULT}
    </span>
  );
}

export function Kpi({ label: l, value, detail, tone: t }: { label: string; value: ReactNode; detail?: ReactNode; tone?: "bad" | "warn" }) {
  return (
    <div className={`card kpi ${t ?? ""}`}>
      <div className="l">{l}</div>
      <div className="v">{value}</div>
      {detail && <div className="d">{detail}</div>}
    </div>
  );
}

export function PageHead({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="row" style={{ alignItems: "flex-start", marginBottom: 16 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <h1>{title}</h1>
        {sub && <p className="sub" style={{ margin: 0 }}>{sub}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </div>
  );
}

export function Loading({ rows = 4 }: { rows?: number }) {
  return (
    <div className="card" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skel" style={{ margin: "10px 0", width: `${90 - i * 12}%` }} />)}
    </div>
  );
}

export function ErrorBox({ error, retry }: { error: ApiError | null; retry?: () => void }) {
  if (!error) return null;
  return (
    <div className="card" role="alert" style={{ borderColor: "var(--bad)" }}>
      <b>{error.status === 403 ? "Not available for your role" : "Something went wrong"}</b>
      <p className="muted" style={{ margin: "6px 0 0" }}>{error.message}</p>
      {retry && error.status !== 403 && <button className="btn sm mt" onClick={retry}>Try again</button>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (open) addEventListener("keydown", esc);
    return () => removeEventListener("keydown", esc);
  }, [open, onClose]);
  return (
    <>
      <div className={`scrim ${open ? "open" : ""}`} onClick={onClose} />
      <section className={`drawer ${open ? "open" : ""}`} role="dialog" aria-modal="true" aria-label={title} aria-hidden={!open}>
        <div className="row">
          <h2 style={{ flex: 1 }}>{title}</h2>
          <button className="btn sm" onClick={onClose} aria-label="Close">✕</button>
        </div>
        {open && children}
      </section>
    </>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    addEventListener("keydown", esc);
    return () => removeEventListener("keydown", esc);
  }, [onClose]);
  return (
    <div className="modal" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="card" role="dialog" aria-modal="true" aria-label={title}>
        <div className="row">
          <h2 style={{ flex: 1 }}>{title}</h2>
          <button className="btn sm" onClick={onClose} aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** A labelled input. `as="select"` takes `options`; `as="textarea"` for long text. */
export function Field({ label: l, name, as = "input", options, full, ...rest }: {
  label: string; name: string; as?: "input" | "select" | "textarea"; options?: (string | [string, string])[]; full?: boolean;
} & Record<string, any>) {
  const id = `f-${name}`;
  return (
    <div className={full ? "full" : undefined}>
      <label htmlFor={id}>{l}</label>
      {as === "select" ? (
        <select id={id} name={name} className="ctl" {...rest}>
          {options?.map((o) => {
            const [v, t] = Array.isArray(o) ? o : [o, label(o)];
            return <option key={v} value={v}>{t}</option>;
          })}
        </select>
      ) : as === "textarea" ? (
        <textarea id={id} name={name} className="ctl" {...rest} />
      ) : (
        <input id={id} name={name} className="ctl" {...rest} />
      )}
    </div>
  );
}

/** Payment terms: "Net" + a digits-only box for the days (15 → "Net 15").
 *  Uncontrolled (defaultValue) inside a <form>, or controlled with value/onChange. */
export function NetTerms({ label = "Payment terms", name, defaultValue, value, onChange, required }: {
  label?: string; name: string; defaultValue?: string | null; value?: string | null;
  onChange?: (value: string) => void; required?: boolean;
}) {
  const digits = (v?: string | null) => (v ?? "").match(/\d{1,3}/)?.[0] ?? "";
  const controlled = value !== undefined;
  const source = controlled ? value : defaultValue;
  const start = digits(source) || (source ? "" : "30");
  const [typed, setTyped] = useState(start);
  const shown = controlled ? (digits(value) || (value == null ? "30" : "")) : typed;
  const set = (raw: string) => {
    const clean = raw.replace(/\D/g, "").slice(0, 3);
    if (!controlled) setTyped(clean);
    onChange?.(clean ? `Net ${clean}` : "");
  };
  return (
    <div>
      <label htmlFor={`f-${name}`}>{label}</label>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span className="muted" aria-hidden="true">Net</span>
        <input id={`f-${name}`} className="ctl" type="text" inputMode="numeric" pattern="[0-9]*"
               maxLength={3} placeholder="30" value={shown} required={required}
               onChange={(e) => set(e.target.value)} style={{ flex: 1 }} />
      </div>
      <input type="hidden" name={name} value={shown ? `Net ${shown}` : (source ?? "")} />
    </div>
  );
}

/** Turns a <form> into a plain object; empty strings are left out. */
export function formValues(form: HTMLFormElement): Record<string, string> {
  const out: Record<string, string> = {};
  new FormData(form).forEach((v, k) => {
    if (typeof v === "string" && v.trim() !== "") out[k] = v.trim();
  });
  return out;
}

// ---------------------------------------------------------------- toasts
const ToastContext = createContext<(message: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);
  const show = useCallback((m: string) => {
    setMessage(m);
    setTimeout(() => setMessage((cur) => (cur === m ? null : cur)), 3500);
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className={`toast ${message ? "show" : ""}`} role="status" aria-live="polite">{message}</div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

/** Runs an action, shows a toast on success and the API's message on failure. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = useCallback(async <T,>(fn: () => Promise<T>, success?: string): Promise<T | undefined> => {
    setBusy(true);
    try {
      const result = await fn();
      if (success) toast(success);
      return result;
    } catch (e) {
      toast((e as Error).message);
      return undefined;
    } finally {
      setBusy(false);
    }
  }, [toast]);
  return { run, busy };
}

export function Avatar({ name, url, size = 32 }: { name?: string | null; url?: string | null; size?: number }) {
  const style = { width: size, height: size, fontSize: size * 0.38 };
  if (url) return <img className="avatar" src={url} alt="" style={{ ...style, objectFit: "cover" }} />;
  return <span className="avatar" style={style} aria-hidden="true">{(name ?? "?").split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase()}</span>;
}

export function Bar({ pct }: { pct: number | null | undefined }) {
  const v = Math.max(0, Math.min(100, Number(pct ?? 0)));
  const t = v >= 90 ? "bad" : v >= 75 ? "warn" : "";
  return <div className={`bar ${t}`} title={`${v}%`}><span style={{ width: `${v}%` }} /></div>;
}
