"use client";

import type { Session } from "@supabase/supabase-js";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, currentTenant, setTenant } from "./api";
import { supabase } from "./supabase";
import { clearCache } from "./useApi";

export type Role =
  | "tenant_admin" | "finance" | "account_manager" | "legal" | "hr" | "approver" | "viewer"
  | "vendor_admin" | "client_user" | "consultant";

export type Workspace = {
  tenant: { id: string; name: string; plan: string; status: string; company_id: string | null };
  is_owner: boolean;
  role: Role;
  company_id: string | null;
  consultant_id: string | null;
  membership_id: string;
  is_platform_admin: boolean;
  can: Record<"see_money" | "see_bill_rate" | "see_pay_rate" | "approve_timesheets" | "manage_contracts" | "manage_people" | "manage_users" | "import_data", boolean>;
};

type Me = {
  profile: { id: string; email: string; full_name: string; headline?: string; avatar_path?: string; avatar_url?: string | null; preferences?: Record<string, any> };
  tenants: { tenant_id: string; tenant_name: string; role: Role; tenant_status: string }[];
  is_platform_admin: boolean;
};

type Ctx = {
  session: Session | null;
  me: Me | null;
  workspace: Workspace | null;
  ready: boolean;
  error: ApiError | null;
  switchTenant: (id: string) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
};

const SessionContext = createContext<Ctx | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const who = await api<Me>("/me");
      setMe(who);
      if (!who.tenants.length) {
        setWorkspace(null);
        return;
      }
      const saved = currentTenant();
      if (!saved || !who.tenants.some((t) => t.tenant_id === saved)) setTenant(who.tenants[0]!.tenant_id);
      setWorkspace(await api<Workspace>("/session"));
    } catch (e) {
      setError(e as ApiError);
    }
  }, []);

  useEffect(() => {
    const sb = supabase();
    sb.auth.getSession().then(async ({ data }) => {
      setSession(data.session);
      if (data.session) await load();
      setReady(true);
    });
    const { data: sub } = sb.auth.onAuthStateChange((event, s) => {
      setSession(s);
      if (event === "SIGNED_OUT") {
        setMe(null);
        setWorkspace(null);
        clearCache();
      }
    });
    return () => sub.subscription.unsubscribe();
  }, [load]);

  const value = useMemo<Ctx>(() => ({
    session, me, workspace, ready, error,
    refresh: load,
    async switchTenant(id: string) {
      setTenant(id);
      clearCache();
      setWorkspace(await api<Workspace>("/session"));
    },
    async signOut() {
      await supabase().auth.signOut();
      setTenant(null);
      clearCache();
      location.href = "/login";
    },
  }), [session, me, workspace, ready, error, load]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Ctx {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside <SessionProvider>");
  return ctx;
}

/** Redirects to sign-in when there is no session. */
export function useRequireSession() {
  const ctx = useSession();
  const router = useRouter();
  useEffect(() => {
    if (ctx.ready && !ctx.session) router.replace(`/login?next=${encodeURIComponent(location.pathname)}`);
  }, [ctx.ready, ctx.session, router]);
  return ctx;
}

export const isStaff = (role?: Role) =>
  !!role && ["tenant_admin", "finance", "account_manager", "legal", "hr", "approver", "viewer"].includes(role);

export function allows(ws: Workspace | null, ...roles: Role[]): boolean {
  return !!ws && (ws.role === "tenant_admin" || roles.includes(ws.role));
}
