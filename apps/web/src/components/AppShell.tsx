"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { allows, isOwner, isStaff, perm, useRequireSession, type Role, type Workspace } from "@/lib/session";
import { Avatar, Loading, useToast } from "./ui";

type Item = { href: string; label: string; show?: (ws: Workspace) => boolean; module?: string };
type Section = { title?: string; items: Item[] };

const staff = (ws: Workspace) => isStaff(ws.role);
const can = (...roles: Role[]) => (ws: Workspace) => allows(ws, ...roles);

const NAV: Section[] = [
  {
    items: [
      { href: "/dashboard", label: "Dashboard", show: staff, module: "dashboard" },
      { href: "/my", label: "My work", show: (ws) => ws.role === "consultant" },
      { href: "/my/timesheet", label: "My timesheet", show: (ws) => ws.role === "consultant" },
      { href: "/my/documents", label: "Policies & documents", show: (ws) => ws.role === "consultant" },
      { href: "/my/requests", label: "Expenses & time off", show: (ws) => ws.role === "consultant" },
      { href: "/partner", label: "Home", show: (ws) => ws.role === "vendor_admin" || ws.role === "client_user" },
    ],
  },
  {
    title: "Money",
    items: [
      { href: "/payments", label: "Payment flow", show: can("finance", "account_manager", "viewer"), module: "invoices" },
      { href: "/invoices", label: "Invoices", show: (ws) => staff(ws), module: "invoices" },
      { href: "/pay", label: "Payroll, 1099 & referrals", show: can("finance", "hr", "approver", "account_manager"), module: "pay" },
    ],
  },
  {
    title: "Work",
    items: [
      { href: "/timesheets", label: "Timesheets", show: (ws) => staff(ws) || ws.role === "vendor_admin", module: "timesheets" },
      { href: "/projects", label: "Projects & placements", show: staff, module: "projects" },
      { href: "/consultants", label: "Consultants", show: staff, module: "consultants" },
      { href: "/companies", label: "Clients & vendors", show: staff, module: "companies" },
    ],
  },
  {
    title: "Contracts & compliance",
    items: [
      { href: "/contracts", label: "MSAs & SOWs", show: staff, module: "contracts" },
      { href: "/esign", label: "E-signatures", show: staff, module: "contracts" },
      { href: "/compliance", label: "Compliance", show: staff, module: "compliance" },
    ],
  },
  { title: "People", items: [{ href: "/network", label: "Network" }, { href: "/businesses", label: "My companies" }] },
  {
    title: "Admin",
    items: [
      { href: "/users", label: "Users & roles", show: can("tenant_admin"), module: "users" },
      { href: "/data", label: "Import & export", show: can("finance", "hr", "legal"), module: "data" },
      { href: "/audit", label: "Audit log", show: can("legal", "finance"), module: "audit" },
      { href: "/settings", label: "Company settings", show: can("tenant_admin"), module: "settings" },
      { href: "/settings/roles", label: "Roles & permissions", show: (ws) => isOwner(ws) },
    ],
  },
];

/** What someone with no workspace yet (a fresh Google/Microsoft sign-up) can open: the network, their own businesses and account. */
const MEMBER_NAV: Section[] = [
  { title: "Your network", items: [{ href: "/network", label: "Feed, people & messages" }, { href: "/businesses", label: "My companies" }] },
  { title: "Account", items: [{ href: "/profile", label: "My profile" }, { href: "/account", label: "Account & security" }] },
];
// Company profiles aren't nav entries, but company members open them from My
// businesses — the API enforces who may see what.
const MEMBER_PATHS = [...MEMBER_NAV.flatMap((s) => s.items.map((i) => i.href)), "/companies"];
const inMemberArea = (path: string) => MEMBER_PATHS.some((p) => path === p || path.startsWith(p + "/"));
// While a new company waits for platform activation it can only finish its profile.
const PENDING_PATHS = [...MEMBER_PATHS, "/companies"];
const inPendingArea = (path: string) => PENDING_PATHS.some((p) => path === p || path.startsWith(p + "/"));

export function AppShell({ children }: { children: ReactNode }) {
  const { ready, session, me, workspace, error, switchTenant, signOut } = useRequireSession();
  const path = usePathname();
  const router = useRouter();
  const noWorkspace = !!me && !me.tenants.length && !me.is_platform_admin;
  // Workspace-only pages (dashboard, invoices …) send a person with no workspace to the feed instead of an error.
  useEffect(() => {
    if (noWorkspace && !inMemberArea(path)) router.replace("/network");
  }, [noWorkspace, path, router]);
  const [navOpen, setNavOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark" | "">("");
  const toast = useToast();
  // T011303-1089: once the myTrakIn team activates a company its owner was waiting on, say so once.
  useEffect(() => {
    const t = workspace?.tenant;
    if (!t?.company_id) return;
    const key = `mytrakin.waiting.${t.id}`;
    try {
      if (t.status === "onboarding") localStorage.setItem(key, "1");
      else if (t.status === "active" && localStorage.getItem(key)) {
        localStorage.removeItem(key);
        toast(`${t.name} has been activated successfully`);
      }
    } catch { /* storage blocked: no toast */ }
  }, [workspace, toast]);

  useEffect(() => {
    try { setTheme((localStorage.getItem("mytrakin.theme") as any) ?? ""); } catch { /* default */ }
  }, []);
  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
  }, [theme]);
  useEffect(() => { setNavOpen(false); setMenuOpen(false); }, [path]);

  const cycleTheme = () => {
    const next = theme === "" ? "dark" : theme === "dark" ? "light" : "";
    setTheme(next);
    try { localStorage.setItem("mytrakin.theme", next); } catch { /* ignore */ }
  };

  if (!ready || !session) return <div className="content"><Loading /></div>;
  if (error) {
    const mfa = error.code === "mfa_required";
    return (
      <div className="auth"><div className="card">
        <h2>{mfa ? "Enter your two-step code" : "We couldn't open your company"}</h2>
        <p className="muted">{mfa
          ? "You turned on two-step verification, so signing in needs the code from your authenticator app."
          : error.message}</p>
        {mfa && <p><Link className="btn pri" href={`/login?step=mfa&next=${encodeURIComponent(path)}`}>Enter code</Link></p>}
        <button className="btn" onClick={signOut}>Sign out</button>
      </div></div>
    );
  }
  if (noWorkspace && !inMemberArea(path)) return <div className="content"><Loading /></div>;
  // T011303-1037: a company still being set up (or waiting for activation) grants no admin role or menus yet.
  // T011303-1084: a rejected company is treated the same way until its owner fixes and resubmits it.
  const settingUp = workspace?.tenant.status === "onboarding" || workspace?.tenant.status === "rejected";
  const pending = settingUp && !inPendingArea(path);

  const name = me?.profile?.full_name ?? me?.profile?.email;
  return (
    <div className="app">
      <a href="#main" className="skip">Skip to content</a>
      <aside className={navOpen ? "open" : ""} aria-label="Main navigation">
        <div className="logo"><i>mT</i>myTrakIn</div>
        <nav className="nav">
          {workspace && !settingUp && NAV.map((sec, i) => {
            const items = sec.items.filter((it) => (!it.show || it.show(workspace)) && (!it.module || perm(workspace, it.module) !== "none"));
            if (!items.length) return null;
            return (
              <div key={i}>
                {sec.title && <div className="sec">{sec.title}</div>}
                {items.map((it) => (
                  <Link key={it.href} href={it.href} className={path === it.href || (it.href !== "/my" && path.startsWith(it.href + "/")) ? "on" : ""}>
                    {it.label}
                  </Link>
                ))}
              </div>
            );
          })}
          {((noWorkspace && !workspace) || settingUp) && MEMBER_NAV.map((sec, i) => (
            <div key={i}>
              <div className="sec">{sec.title}</div>
              {sec.items.map((it) => (
                <Link key={it.href} href={it.href} className={inMemberArea(path) && (path === it.href || path.startsWith(it.href + "/")) ? "on" : ""}>
                  {it.label}
                </Link>
              ))}
            </div>
          ))}
          {me?.is_platform_admin && (
            <>
              <div className="sec">Platform</div>
              <Link href="/platform" className={path.startsWith("/platform") ? "on" : ""}>Platform admin</Link>
            </>
          )}
        </nav>
      </aside>
      <main id="main">
        <header>
          <button className="btn menu-btn" onClick={() => setNavOpen((o) => !o)} aria-label="Menu">☰</button>
          {me && me.tenants.length > 1 ? (
            <select className="ctl" value={workspace?.tenant.id} onChange={(e) => switchTenant(e.target.value)} aria-label="Company">
              {me.tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
            </select>
          ) : (
            <b style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }}>{workspace?.tenant.name ?? (noWorkspace ? "Your network" : "")}</b>
          )}
          <span className="grow" />
          <button className="btn sm" onClick={cycleTheme} title="Theme: system, dark or light">
            {theme === "dark" ? "Dark" : theme === "light" ? "Light" : "Auto"}
          </button>
          <button className="btn sm" onClick={() => setMenuOpen((o) => !o)} aria-haspopup="menu" aria-expanded={menuOpen}
                  style={{ display: "flex", gap: 8, alignItems: "center", border: 0, background: "none" }}>
            <Avatar name={name} url={me?.profile?.avatar_url ?? null} size={30} />
            <span className="hide-sm">{name}</span>
          </button>
        </header>
        <div className={`amenu ${menuOpen ? "open" : ""}`} role="menu">
          <div style={{ padding: "8px 10px" }}>
            <b>{name}</b>
            <div className="muted" style={{ fontSize: 12.5 }}>{workspace && !settingUp ? `${workspace.role.replace(/_/g, " ")} · ` : ""}{me?.profile?.email}</div>
          </div>
          <Link href="/profile" role="menuitem">My profile</Link>
          <Link href="/account" role="menuitem">Account & security</Link>
          <a role="menuitem" onClick={signOut}>Sign out</a>
        </div>
        <div className="content">{pending && workspace ? (
          <div className="card">
            {workspace.tenant.status === "rejected" ? <>
              <h2>{workspace.tenant.name} was not activated</h2>
              <p className="muted">The myTrakIn team rejected it{workspace.tenant.decision_note ? <>: “{workspace.tenant.decision_note}”</> : ""}.
                Fix the company profile and resubmit it, or create another company from My companies.</p>
            </> : workspace.tenant.company_id ? <>
              <h2>Waiting for activation</h2>
              <p className="muted">The myTrakIn team is reviewing {workspace.tenant.name}. We&apos;ll e-mail you as soon as it&apos;s active.
                Meanwhile you can complete your company profile.</p>
            </> : <>
              <h2>Your company isn&apos;t set up yet</h2>
              <p className="muted">Finish creating it from My companies. Until it is submitted and activated you have no admin access.</p>
              <p><Link className="btn pri" href="/businesses">Go to My companies</Link></p>
            </>}
            {workspace.tenant.company_id && <p><Link className="btn pri" href={`/companies/${workspace.tenant.company_id}`}>Open company profile</Link></p>}
          </div>
        ) : children}</div>
      </main>
      <div className={`scrim ${navOpen ? "open" : ""}`} onClick={() => setNavOpen(false)} />
    </div>
  );
}
