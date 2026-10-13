"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import type { ApiError } from "@/lib/api";
import { label, tone } from "@/lib/format";

export function Chip({ status, children }: { status?: string | null; children?: ReactNode }) {
  return <span className={`chip ${tone(status)}`}>{children ?? label(status)}</span>;
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
