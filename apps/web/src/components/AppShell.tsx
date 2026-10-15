"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { allows, isStaff, useRequireSession, type Role, type Workspace } from "@/lib/session";
import { Avatar, Loading } from "./ui";

type Item = { href: string; label: string; show?: (ws: Workspace) => boolean };
type Section = { title?: string; items: Item[] };

const staff = (ws: Workspace) => isStaff(ws.role);
const can = (...roles: Role[]) => (ws: Workspace) => allows(ws, ...roles);

const NAV: Section[] = [
  {
    items: [
      { href: "/dashboard", label: "Dashboard", show: staff },
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
      { href: "/payments", label: "Payment flow", show: can("finance", "account_manager", "viewer") },
      { href: "/invoices", label: "Invoices", show: (ws) => staff(ws) },
      { href: "/pay", label: "Payroll, 1099 & referrals", show: can("finance", "hr", "approver", "account_manager") },
    ],
  },
  {
    title: "Work",
    items: [
      { href: "/timesheets", label: "Timesheets", show: (ws) => staff(ws) || ws.role === "vendor_admin" },
      { href: "/projects", label: "Projects & placements", show: staff },
      { href: "/consultants", label: "Consultants", show: staff },
      { href: "/companies", label: "Clients & vendors", show: staff },
    ],
  },
  {
    title: "Contracts & compliance",
    items: [
      { href: "/contracts", label: "MSAs & SOWs", show: staff },
      { href: "/esign", label: "E-signatures", show: staff },
      { href: "/compliance", label: "Compliance", show: staff },
    ],
  },
  { title: "People", items: [{ href: "/network", label: "Network" }, { href: "/businesses", label: "My businesses" }] },
  {
    title: "Admin",
    items: [
      { href: "/users", label: "Users & roles", show: can("tenant_admin") },
      { href: "/data", label: "Import & export", show: can("finance", "hr", "legal") },
      { href: "/audit", label: "Audit log", show: can("legal", "finance") },
      { href: "/settings", label: "Workspace settings", show: can("tenant_admin") },
    ],
  },
];

/** What someone with no workspace yet (a fresh Google/Microsoft sign-up) can open: the network, their own businesses and account. */
const MEMBER_NAV: Section[] = [
  { title: "Your network", items: [{ href: "/network", label: "Feed, people & messages" }, { href: "/businesses", label: "My businesses" }] },
  { title: "Account", items: [{ href: "/profile", label: "My profile" }, { href: "/account", label: "Account & security" }] },
];
// Company profiles aren't nav entries, but company members open them from My
// businesses — the API enforces who may see what.
const MEMBER_PATHS = [...MEMBER_NAV.flatMap((s) => s.items.map((i) => i.href)), "/companies"];
const inMemberArea = (path: string) => MEMBER_PATHS.some((p) => path === p || path.startsWith(p + "/"));

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
        <h2>{mfa ? "Two-step verification required" : "We couldn't open your workspace"}</h2>
        <p className="muted">{mfa
          ? "Your role handles money, so signing in needs a second step. Set up your authenticator app — it takes a minute, and you only do it once per device."
          : error.message}</p>
        {mfa && <p><Link className="btn pri" href={`/login?step=mfa&next=${encodeURIComponent(path)}`}>Set up two-step verification</Link></p>}
        <button className="btn" onClick={signOut}>Sign out</button>
      </div></div>
    );
  }
  if (noWorkspace && !inMemberArea(path)) return <div className="content"><Loading /></div>;

  const name = me?.profile?.full_name ?? me?.profile?.email;
  return (
    <div className="app">
      <a href="#main" className="skip">Skip to content</a>
      <aside className={navOpen ? "open" : ""} aria-label="Main navigation">
        <div className="logo"><i>mT</i>myTrakIn</div>
        <nav className="nav">
          {workspace && NAV.map((sec, i) => {
            const items = sec.items.filter((it) => !it.show || it.show(workspace));
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
          {noWorkspace && !workspace && MEMBER_NAV.map((sec, i) => (
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
              <Link href="/platform" className={path.startsWith("/platform") ? "on" : ""}>Owner console</Link>
            </>
          )}
        </nav>
      </aside>
      <main id="main">
        <header>
          <button className="btn menu-btn" onClick={() => setNavOpen((o) => !o)} aria-label="Menu">☰</button>
          {me && me.tenants.length > 1 ? (
            <select className="ctl" value={workspace?.tenant.id} onChange={(e) => switchTenant(e.target.value)} aria-label="Workspace">
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
            <div className="muted" style={{ fontSize: 12.5 }}>{workspace ? `${workspace.role.replace(/_/g, " ")} · ` : ""}{me?.profile?.email}</div>
          </div>
          <Link href="/profile" role="menuitem">My profile</Link>
          <Link href="/account" role="menuitem">Account & security</Link>
          <a role="menuitem" onClick={signOut}>Sign out</a>
        </div>
        <div className="content">{children}</div>
      </main>
      <div className={`scrim ${navOpen ? "open" : ""}`} onClick={() => setNavOpen(false)} />
    </div>
  );
}
