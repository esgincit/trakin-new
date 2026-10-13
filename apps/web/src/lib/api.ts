import { supabase } from "./supabase";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "") + "/v1";
const TENANT_KEY = "mytrakin.tenant";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

export function currentTenant(): string | null {
  try {
    return localStorage.getItem(TENANT_KEY);
  } catch {
    return null;
  }
}

export function setTenant(id: string | null) {
  try {
    if (id) localStorage.setItem(TENANT_KEY, id);
    else localStorage.removeItem(TENANT_KEY);
  } catch {
    /* private mode: the first workspace is used */
  }
}

type Options = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;              // sent as JSON
  form?: FormData;             // sent as multipart (file uploads)
  query?: Record<string, string | number | boolean | null | undefined>;
  auth?: boolean;              // false for public pages (signing, registration)
  raw?: boolean;               // return the Response (downloads)
};

async function headers(auth: boolean): Promise<Record<string, string>> {
  const h: Record<string, string> = {};
  if (!auth) return h;
  const { data } = await supabase().auth.getSession();
  if (data.session) h.Authorization = `Bearer ${data.session.access_token}`;
  const tenant = currentTenant();
  if (tenant) h["X-Tenant-Id"] = tenant;
  return h;
}

export function url(path: string, query?: Options["query"]): string {
  const u = new URL(API_URL + path);
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== "") u.searchParams.set(k, String(v));
  }
  return u.toString();
}

/** Calls the myTrakIn API and returns parsed JSON. Errors become ApiError with a readable message. */
export async function api<T = any>(path: string, opts: Options = {}): Promise<T> {
  const h = await headers(opts.auth !== false);
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    body = JSON.stringify(opts.body);
    h["Content-Type"] = "application/json";
  }
  let res: Response;
  try {
    res = await fetch(url(path, opts.query), { method: opts.method ?? (body ? "POST" : "GET"), headers: h, body });
  } catch {
    throw new ApiError(0, "offline", "Can't reach myTrakIn. Check your connection and try again.");
  }
  if (opts.raw && res.ok) return res as unknown as T;
  if (!res.ok) {
    let code = "error", message = `Request failed (${res.status})`;
    try {
      const j = await res.json();
      code = j.error?.code ?? code;
      message = j.error?.message ?? message;
    } catch {
      /* not JSON */
    }
    if (res.status === 401 && typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
      location.href = `/login?next=${encodeURIComponent(location.pathname + location.search)}`;
    }
    if (code === "mfa_required" && typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
      location.href = `/login?step=mfa&next=${encodeURIComponent(location.pathname)}`;
    }
    throw new ApiError(res.status, code, message);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

/** Downloads a file from the API (CSV export, templates) with the user's credentials. */
export async function download(path: string, filename: string, query?: Options["query"]) {
  const res = await api<Response>(path, { raw: true, query });
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
