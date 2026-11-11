"use client";

/* The Network tab re-imagined as an international-standard social workspace:
   a sticky "me" rail, a LinkedIn-style feed with a real composer, people
   discovery cards, an invitation-driven My-network page and a messenger with
   bubbles and day separators. All behaviors (invite withdraw, polling,
   deep-links) are preserved from the previous version. */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Avatar, ErrorBox, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { relTime } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";
import "./network.css";

type Tab = "feed" | "people" | "connections" | "messages";
const TABS: Tab[] = ["feed", "people", "connections", "messages"];

/** Shape of GET /network/connections. */
type Net = { connections: any[]; incoming: any[]; outgoing: any[]; pending_in: number; pending_out: number };

/* ---------------------------------------------------------------- icons */
const svg = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "currentColor" } as const;
const Icons = {
  feed: <svg {...svg}><path d="M4 4h16a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Zm1 4v10h14V8H5Zm2 2h4v4H7v-4Zm6 0h4v1.5h-4V10Zm0 2.5h4V14h-4v-1.5Z" /></svg>,
  people: <svg {...svg}><path d="M8.5 11a3.5 3.5 0 1 1 0-7 3.5 3.5 0 0 1 0 7Zm7 0a3 3 0 1 1 0-6 3 3 0 0 1 0 6ZM2 19c0-3 3-5 6.5-5s6.5 2 6.5 5v1H2v-1Zm14-4.6c2.4.4 6 1.8 6 4.6v1h-5v-1c0-1.5-.4-2.7-1-3.6Z" /></svg>,
  connections: <svg {...svg}><path d="M12 2 3 6.5V12c0 5 3.8 8.7 9 10 5.2-1.3 9-5 9-10V6.5L12 2Zm-1 14-3-3 1.4-1.4L11 13.2l4.6-4.6L17 10l-6 6Z" /></svg>,
  messages: <svg {...svg}><path d="M4 4h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H8l-4 4V5a1 1 0 0 1 1-1Zm3 4a1.25 1.25 0 1 0 0 2.5A1.25 1.25 0 0 0 7 8Zm5 0a1.25 1.25 0 1 0 0 2.5A1.25 1.25 0 0 0 12 8Zm5 0a1.25 1.25 0 1 0 0 2.5A1.25 1.25 0 0 0 17 8Z" /></svg>,
  search: <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>,
  globe: <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.6 2.6 2.6 15.4 0 18M12 3c-2.6 2.6-2.6 15.4 0 18" /></svg>,
  thumbs: <svg width={16} height={16} viewBox="0 0 24 24" fill="currentColor"><path d="M2 10h3v10H2a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1Zm5.5 10.2 5.8-1.9a2 2 0 0 0 1.36-1.77l.4-4.53h3.74c1.3 0 2.3-1.17 2.1-2.45l-.75-4.5A2.13 2.13 0 0 0 18.05 3H9.4A1.4 1.4 0 0 0 8 4.4v13.6l-.5.2Z" /></svg>,
  trash: <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round"><path d="M4 7h16M9 7V4h6v3m-9 0 1 13h10l1-13M10 11v6M14 11v6" /></svg>,
  send: <svg width={16} height={16} viewBox="0 0 24 24" fill="currentColor"><path d="M2 21 23 12 2 3v7l15 2-15 2v7Z" /></svg>,
  back: <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round"><path d="M15 5 8 12l7 7" /></svg>,
  check: <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round"><path d="m4 12.5 5 5L20 6.5" /></svg>,
  x: <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round"><path d="M5 5l14 14M19 5 5 19" /></svg>,
};
const Ico = ({ n, size = 18, ...rest }: { n: keyof typeof Icons; size?: number } & React.HTMLAttributes<HTMLElement>) => {
  const el = Icons[n];
  return <span style={{ display: "grid", placeItems: "center" }} {...rest}>{el}</span>;
};

export default function NetworkPage() {
  return <Suspense><Network /></Suspense>;
}

function Network() {
  const params = useSearchParams();
  const p = params.get("tab") as Tab | null;
  const [tab, setTab] = useState<Tab>(p && TABS.includes(p) ? p : "feed");
  // Deep links (?tab=…&with=…) and in-page <Link>navigations should keep the
  // tab in step with the URL without reloading the page.
  useEffect(() => { if (p && TABS.includes(p) && p !== tab) setTab(p); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [params]);
  const invites = useApi<Net>("/network/connections");
  const threads = useApi<any[]>("/network/messages");
  const pending = invites.data?.incoming?.length ?? 0;
  const unread = (threads.data ?? []).reduce((n: number, t: any) => n + (t.unread > 0 ? 1 : 0), 0);
  return (
    <>
      <PageHead title="Network" sub="Your professional profile, colleagues across companies you work with, updates and messages." actions={<Link className="btn" href="/profile">My profile</Link>} />
      <nav className="nw-tabs" aria-label="Network sections">
        {([["feed", "Feed", "feed"], ["people", "People", "people"], ["connections", "My network", "connections"], ["messages", "Messaging", "messages"]] as const).map(([t, l, icon]) => (
          <button key={t} className={`nw-tab${tab === t ? " on" : ""}`} onClick={() => setTab(t as Tab)} aria-current={tab === t ? "page" : undefined}>
            <Ico n={icon as any} size={16} />{l}
            {t === "connections" && pending > 0 && <span className="cnt">{pending}</span>}
            {t === "messages" && unread > 0 && <span className="dot" aria-label={`${unread} conversations with unread messages`} />}
          </button>
        ))}
      </nav>
      <div className="nw-shell">
        <NetMe invites={invites.data} />
        <div className="nw-main">
          {tab === "feed" && <Feed />}
          {tab === "people" && <People />}
          {tab === "connections" && <Connections invites={invites} />}
          {tab === "messages" && <Messages initial={params.get("with")} threads={threads} />}
        </div>
      </div>
    </>
  );
}

/** Sticky left rail with my identity and live network numbers. */
function NetMe({ invites }: { invites?: Net }) {
  const me = useApi<any>("/network/me");
  const d = me.data;
  return (
    <aside className="nw-me">
      <div className="cov" aria-hidden />
      <div className="top">
        <span className="avwrap"><Avatar name={d?.full_name} url={d?.avatar_url} size={72} /></span>
        <Link className="nm" href="/profile">{d?.full_name ?? "…"}</Link>
        <div className="hl">{d?.headline ?? ""}</div>
        {d?.location && <div className="muted" style={{ fontSize: 12 }}><Ico n="globe" /> {d.location}</div>}
      </div>
      <div className="stats">
        <a className="stat" href="?tab=connections" style={{ display: "block", color: "inherit", textDecoration: "none" }}>
          <b>{invites?.connections?.length ?? "—"}</b><span>Connections</span>
        </a>
        <a className="stat" href="?tab=connections" style={{ display: "block", color: "inherit", textDecoration: "none" }}>
          <b>{invites?.incoming?.length ?? "—"}</b><span>Invitations</span>
        </a>
      </div>
      <footer>
        <Link href="/profile">Edit profile</Link>
        <Link href="/account">Account &amp; security</Link>
      </footer>
    </aside>
  );
}

/** Keep connection state current without a manual refresh: poll while visible, and again when the tab regains focus. */
function useLiveReload(reload: () => void) {
  useEffect(() => {
    const tick = () => { if (document.visibilityState === "visible") reload(); };
    const t = setInterval(tick, 15000);
    document.addEventListener("visibilitychange", tick);
    return () => { clearInterval(t); document.removeEventListener("visibilitychange", tick); };
  }, [reload]);
}

/* --------------------------------------------------------------------------- feed */

const KIND_LABEL: Record<string, string> = { kudos: "Kudos", opening: "Opening", announcement: "Announcement" };
const FEED_PAGE = 15;

function Feed() {
  const { workspace, me } = useSession();
  const { data, error, reload } = useApi<any[]>("/network/feed");
  const [extra, setExtra] = useState<any[]>([]);          // older pages appended below the first
  const [noMore, setNoMore] = useState(false);
  const [liked, setLiked] = useState<Set<string>>(new Set());
  const { run, busy } = useAction();

  // First page plus everything we paged in, without duplicates (a reload can
  // pull an appended post back into the fresh first page).
  const posts = useMemo(() => {
    const base = data ?? [];
    const seen = new Set(base.map((x) => x.id));
    return [...base, ...extra.filter((x) => !seen.has(x.id))];
  }, [data, extra]);
  const hasMore = !noMore && posts.length >= FEED_PAGE;

  const loadMore = async () => {
    const last = posts[posts.length - 1];
    if (!last) return;
    const rows = await run(() => api<any[]>("/network/feed", { query: { before: last.created_at, limit: FEED_PAGE } }));
    if (!rows) return;                                   // run() already toasted the error
    if (rows.length < FEED_PAGE) setNoMore(true);
    const seen = new Set(posts.map((x) => x.id));
    const fresh = rows.filter((r: any) => !seen.has(r.id));
    if (fresh.length) setExtra((x) => [...x, ...fresh]);
  };

  const like = async (p: any) => {
    if (liked.has(p.id)) return;
    setLiked((s) => new Set(s).add(p.id));               // optimistic highlight
    const res = await run(() => api(`/network/posts/${p.id}/like`, { method: "POST" }));
    // The server counted our like, so a refreshed count already includes it —
    // drop the optimistic tag either way (on failure run() toasted and this is
    // the revert, never mutating the set in place).
    setLiked((s) => { const n = new Set(s); n.delete(p.id); return n; });
    if (res?.likes !== undefined) reload();
  };

  return (
    <div className="nw-feed">
      {!workspace && (
        <div className="nw-ad">
          <span>👋</span>
          <p style={{ margin: 0 }}>
            <b>Welcome!</b> You can post, connect and message right away. To use payments, timesheets and contracts,
            ask your administrator to invite <b>{me?.profile?.email}</b>, or <Link href="/businesses">create your company</Link>.
            Tip: add two-step verification under <Link href="/account">Account &amp; security</Link>.
          </p>
        </div>
      )}
      <Composer onPosted={reload} />
      <ErrorBox error={error} retry={reload} />
      {posts.map((p: any) => (
        <article key={p.id} className="nw-post" data-kind={p.kind}>
          <div className="nw-ph">
            <Avatar name={p.author} url={p.avatar_url} size={44} />
            <div className="who">
              <div className="row" style={{ gap: 6 }}>
                <Link href={`/network/${p.author_id}`}>{p.author}</Link>
                {p.kind !== "update" && <span className={`nw-kind ${p.kind}`}>{KIND_LABEL[p.kind]}</span>}
                {p.mine && <button className="nw-btn quiet" title="Delete this post" style={{ padding: "2px 8px", border: 0 }}
                  onClick={async () => { if (confirm("Delete this post?")) { await run(() => api(`/network/posts/${p.id}`, { method: "DELETE" }), "Deleted"); reload(); } }}>
                  <Ico n="trash" size={14} />
                </button>}
              </div>
              <div className="meta">{p.headline}<span>·</span>{relTime(p.created_at)}
                {p.network_wide && <span className="nw-netw" title="Shared with everyone in your network"><Ico n="globe" /></span>}
              </div>
            </div>
          </div>
          <div className="nw-pb">{p.body}</div>
          <div className="nw-acts">
            <button className={`nw-act${liked.has(p.id) ? " liked" : ""}`} title={liked.has(p.id) ? "Already liked" : "Like this post"}
              disabled={liked.has(p.id)} onClick={() => like(p)}>
              <span className="ico"><Ico n="thumbs" size={15} /></span>
              <span className="nw-lbl">Like</span>
              <span>{p.likes + (liked.has(p.id) ? 1 : 0)}</span>
            </button>
          </div>
        </article>
      ))}
      {hasMore && (
        <div style={{ textAlign: "center" }}>
          <button className="nw-btn" data-wait={busy ? 1 : undefined} disabled={busy} onClick={loadMore}>
            {busy ? "Loading…" : "Load more"}
          </button>
        </div>
      )}
      {data && !posts.length && <div className="nw-post"><div className="nw-empty">No posts yet — be the first to share an update.</div></div>}
    </div>
  );
}

/* Composer: collapsed until clicked, like every modern social composer. */
function Composer({ onPosted }: { onPosted: () => void }) {
  const { workspace } = useSession();
  const me = useApi<any>("/network/me");
  const [open, setOpen] = useState(false);
  const [body, setBody] = useState("");
  const [kind, setKind] = useState("update");
  const [audience, setAudience] = useState(workspace ? "company" : "network");
  const { run, busy } = useAction();
  useEffect(() => { if (open) document.querySelector<HTMLTextAreaElement>(".nw-comp textarea")?.focus(); }, [open]);
  return (
    <form className="nw-comp" onSubmit={async (e) => { e.preventDefault(); if (await run(() => api("/network/posts", { body: { body, kind, audience } }), "Posted")) { setBody(""); setOpen(false); onPosted(); } }}>
      {!open ? (
        <div role="button" tabIndex={0} aria-label="Start a post" onClick={() => setOpen(true)} onKeyDown={(e) => e.key === "Enter" && setOpen(true)}>
          <Avatar name={me.data?.full_name} url={me.data?.avatar_url} size={38} />
          Start a post, share an opening or thank a colleague…
        </div>
      ) : (
        <>
          <div className="box">
            <Avatar name={me.data?.full_name} url={me.data?.avatar_url} size={38} />
            <textarea value={body} onChange={(e) => setBody(e.target.value)} maxLength={3000}
              placeholder={kind === "opening" ? "Describe the role: team, remote or on-site, and how to apply…" : "What do you want to say?"} />
          </div>
          <div className="opts">
            <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Post type">
              <option value="update">Any update</option><option value="kudos">🎉 Kudos</option><option value="opening">💼 Job opening</option>
              {allows(workspace, "hr") && <option value="announcement">📣 Announcement</option>}
            </select>
            <select value={audience} onChange={(e) => setAudience(e.target.value)} aria-label="Audience">
              {workspace && <option value="company">◉ {workspace.tenant.name}</option>}
              <option value="network">🌐 Everyone in my network</option>
            </select>
            <span className="nw-count">{body.length}/3000</span>
            <button type="button" className="nw-btn quiet" onClick={() => { setOpen(false); setBody(""); }}>Cancel</button>
            <button className="nw-btn pri" disabled={busy || !body.trim()}>Post</button>
          </div>
        </>
      )}
    </form>
  );
}

/* --------------------------------------------------------------------------- people */

function People() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [otw, setOtw] = useState(false);
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 300); return () => clearTimeout(t); }, [q]);
  const { data, error, loading, reload } = useApi<any[]>("/network/people", { q: debounced || undefined, open_to_work: otw || undefined }, { fresh: true });
  const { run } = useAction();
  useLiveReload(reload);
  const act = (p: any, fn: () => Promise<unknown>, msg: string) => async (e: any) => { e.stopPropagation(); await run(fn, msg); reload(); };
  return (
    <div>
      <div className="nw-search" role="search">
        <Ico n="search" size={16} />
        <input type="search" placeholder="Search by name, skill, title or city…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search people" />
      </div>
      <div className="nw-filters">
        <button type="button" className={`nw-fchip${otw ? " on" : ""}`} onClick={() => setOtw(!otw)} aria-pressed={otw}>
          {otw && <Ico n="check" size={12} />} Open to work
        </button>
        {data && <span className="nw-nres">{data.length} {data.length === 1 ? "person" : "people"}</span>}
      </div>
      <ErrorBox error={error} retry={reload} />
      {loading && <div className="nw-skels">{[0, 1, 2, 3].map((i) => <div key={i} className="nw-skelcard skel" />)}</div>}
      <div className="nw-cards">
        {data?.map((p) => (
          <div key={p.id} className="nw-person" role="link" tabIndex={0} onClick={() => router.push(`/network/${p.id}`)}
            onKeyDown={(e) => e.key === "Enter" && router.push(`/network/${p.id}`)}>
            <div className="cov" aria-hidden />
            {p.open_to_work && <span className="otw">Open to work</span>}
            <div className="top">
              <span className="avwrap"><Avatar name={p.full_name} url={p.avatar_url} size={64} /></span>
              <span className="nm">{p.full_name}</span>
              <div className="hl">{p.headline}</div>
              {p.location && <div className="loc">{p.location}</div>}
            </div>
            <div className="skills">{(p.skills ?? []).slice(0, 4).map((s: string) => <span key={s}>{s}</span>)}{(p.skills ?? []).length > 4 && <span>+{p.skills.length - 4}</span>}</div>
            <footer>
              {(!p.connection || (p.connection === "declined" && !p.i_asked)) &&
                <button className="nw-btn ghost" onClick={act(p, () => api(`/network/connections/${p.id}`, { method: "POST" }), "Invitation sent")}><Ico n="check" size={13} /> Connect</button>}
              {p.connection === "pending" && !p.i_asked &&
                <button className="nw-btn pri" onClick={act(p, () => api(`/network/connections/${p.id}/respond`, { method: "POST", query: { accept: true } }), "Connected")}><Ico n="check" size={13} /> Accept</button>}
              {p.connection === "accepted" && <span className="chip good">Connected</span>}
              {p.i_asked && p.connection !== "accepted" &&
                <button className="nw-btn quiet" title="Click to withdraw this request" onClick={act(p, () => api(`/network/connections/${p.id}`, { method: "DELETE" }), "Request withdrawn")}>
                  Pending…</button>}
            </footer>
          </div>
        ))}
      </div>
      {data && !data.length && <div className="nw-empty">No one matches — try a different name, skill or city.</div>}
    </div>
  );
}

/* ------------------------------------------------------------------------ my network */

function Connections({ invites }: { invites: ReturnType<typeof useApi<Net>> }) {
  const { data, error, reload } = invites;
  const { run } = useAction();
  const [q, setQ] = useState("");
  useLiveReload(reload);
  if (!data && error) return <ErrorBox error={error} retry={reload} />;
  if (!data) return <div className="nw-post"><div className="skel" style={{ height: 120 }} /></div>;
  const needle = q.trim().toLowerCase();
  const connections = data.connections.filter((p: any) => !needle || `${p.full_name} ${p.headline}`.toLowerCase().includes(needle));
  return (
    <div className="nw-feed">
      <section className="nw-box nw-invites">
        <h3>Invitations <span className="chip brand">{data.incoming.length}</span></h3>
        {data.incoming.map((p: any) => (
          <div key={p.id} className="nw-row">
            <Avatar name={p.full_name} url={p.avatar_url} size={44} />
            <div className="who"><Link href={`/network/${p.id}`}>{p.full_name}</Link><small>{p.headline}</small></div>
            <div className="acts">
              <button className="nw-btn pri" onClick={async () => { await run(() => api(`/network/connections/${p.id}/respond`, { method: "POST", query: { accept: true } }), "Connected"); reload(); }}><Ico n="check" size={13} /> Accept</button>
              <button className="nw-btn" title="Ignore invitation" onClick={async () => { await run(() => api(`/network/connections/${p.id}/respond`, { method: "POST", query: { accept: false } })); reload(); }}><Ico n="x" size={13} /></button>
            </div>
          </div>
        ))}
        {!data.incoming.length && <div className="nw-empty">No invitations right now. People you meet will show up here.</div>}
      </section>

      <div className="nw-stats">
        <div><b>{data.connections.length}</b><span>Connections</span></div>
        <div><b>{data.pending_in}</b><span>Received</span></div>
        <div><b>{data.pending_out}</b><span>Sent</span></div>
      </div>

      {data.outgoing.length > 0 && (
        <section className="nw-box">
          <h3>Sent — waiting for a reply <span className="chip">{data.outgoing.length}</span></h3>
          {data.outgoing.map((p: any) => (
            <div key={p.id} className="nw-row">
              <Avatar name={p.full_name} url={p.avatar_url} /><div className="who"><Link href={`/network/${p.id}`}>{p.full_name}</Link><small>{p.headline}</small></div>
              <div className="acts">
                <button className="nw-btn" onClick={async () => { await run(() => api(`/network/connections/${p.id}`, { method: "DELETE" }), "Request withdrawn"); reload(); }}>Withdraw</button>
              </div>
            </div>
          ))}
        </section>
      )}

      <section className="nw-box">
        <div className="row" style={{ marginBottom: 4 }}>
          <h3 style={{ margin: 0 }}>Connections</h3>
          <div className="nw-search" style={{ margin: 0, padding: "5px 12px" }}>
            <Ico n="search" size={13} />
            <input type="search" placeholder="Search connections…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter connections" />
          </div>
        </div>
        {connections.map((p: any) => (
          <div key={p.id} className="nw-row">
            <Avatar name={p.full_name} url={p.avatar_url} /><div className="who"><Link href={`/network/${p.id}`}>{p.full_name}</Link><small>{p.headline}</small></div>
            <div className="acts">
              <Link className="nw-btn" href={`/network?tab=messages&with=${p.id}`}>Message</Link>
            </div>
          </div>
        ))}
        {!connections.length && <div className="nw-empty">{data.connections.length ? "No connections match your search." : "Connect with colleagues, consultants and partners from the People tab."}</div>}
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------------- messaging */

function Messages({ initial, threads: threadsHook }: { initial: string | null; threads: ReturnType<typeof useApi<any[]>> }) {
  const threads = threadsHook.data ?? [];
  // Only a person id from the link goes into the API path, never other text (it would change which endpoint is called).
  const [withId, setWithId] = useState<string | null>(initial && /^[0-9a-f-]{36}$/i.test(initial) ? initial : null);
  const [q, setQ] = useState("");
  const convo = useApi<any[]>(withId ? `/network/messages/${withId}` : null);
  const person = useApi(withId && !threads.some((t: any) => t.person_id === withId) ? `/network/people/${withId}` : null);
  const [text, setText] = useState("");
  const { run, busy } = useAction();
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [convo.data]);
  useEffect(() => {
    if (!withId) return;
    const t = setInterval(convo.reload, 15000);   // light polling while a conversation is open
    return () => clearInterval(t);
  }, [withId, convo.reload]);
  const current = useMemo(
    () => threads.find((t: any) => t.person_id === withId) ?? person.data,
    [threads, withId, person.data]);
  const needle = q.trim().toLowerCase();
  const filtered = threads.filter((t: any) => !needle || `${t.full_name} ${t.last_message ?? ""}`.toLowerCase().includes(needle));
  return (
    <div className="nw-chat">
      <div className={`nw-tlist${withId ? "" : " solo"}`}>
        <div className="hd">
          Chats
          <div className="search">
            <Ico n="search" size={13} />
            <input placeholder="Search conversations…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search messages" />
          </div>
        </div>
        <div className="nw-tscroll">
          {filtered.map((t: any) => (
            <div key={t.person_id} className={`nw-titem${t.person_id === withId ? " on" : ""}`} data-unread={t.unread > 0 ? 1 : 0}
              onClick={() => setWithId(t.person_id)} role="button" tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && setWithId(t.person_id)}>
              <Avatar name={t.full_name} url={t.avatar_url} size={40} />
              <div className="who">
                <div className="t"><b>{t.full_name}</b><time>{relTime(t.last_at)}</time></div>
                <div className="prev">{t.unread > 0 && <span>{t.unread} new</span>}{t.last_message}</div>
              </div>
              {t.unread > 0 && <span className="nw-badge">{t.unread}</span>}
            </div>
          ))}
          {threadsHook.data && !filtered.length && <div className="nw-empty" style={{ padding: 16 }}>No conversations match.</div>}
        </div>
      </div>
      <div className="nw-convo">
        {withId ? (
          <>
            <div className="nw-chead">
              <button className="nw-back" aria-label="Back to conversations" onClick={() => setWithId(null)}><Ico n="back" size={16} /></button>
              <Avatar name={current?.full_name} url={current?.avatar_url} size={34} />
              <div className="who"><b>{current?.full_name ?? "…"}</b><small>{current?.headline}</small></div>
              <Link href={`/network/${withId}`} className="nw-btn" style={{ borderRadius: 99, padding: "5px 12px" }}>View profile</Link>
            </div>
            <div className="nw-bubbles" role="log" aria-live="polite" aria-label={`Messages with ${current?.full_name ?? ""}`}>
              {convo.data?.map((m: any, i: number, all: any[]) => {
                const day = new Date(m.created_at).toDateString();
                const prev = i > 0 ? new Date(all[i - 1].created_at).toDateString() : null;
                return (
                  <div key={m.id} className={`nw-msg${m.mine ? " me" : ""}`}>
                    {prev !== day && <span className="nw-day">{dayLabel(m.created_at)}</span>}
                    <span className="bub">{m.body}<time>{tstamp(m.created_at)}{m.mine ? " · Sent" : ""}</time></span>
                  </div>
                );
              })}
              {convo.data && !convo.data.length && <div className="nw-empty">No messages yet — say hello 👋</div>}
              <div ref={end} />
            </div>
            <form className="nw-minput" onSubmit={async (e) => {
              e.preventDefault();
              if (await run(() => api(`/network/messages/${withId}`, { body: { body: text } }))) { setText(""); convo.reload(); threadsHook.reload(); }
            }}>
              <input autoComplete="off" value={text} onChange={(e) => setText(e.target.value)} placeholder="Write a message…" aria-label="Message" />
              <button className="nw-send" disabled={busy || !text.trim()} aria-label="Send message"><Ico n="send" size={16} /></button>
            </form>
          </>
        ) : <EmptyThread />}
      </div>
    </div>
  );
}

function EmptyThread() {
  return (
    <div className="nw-empty">
      <div style={{ fontSize: 40, marginBottom: 8 }}>💬</div>
      <b>Your messages</b>
      <p style={{ margin: "4px 0 0" }}>Choose a conversation on the left, or message someone<br />from the People tab or their profile.</p>
    </div>
  );
}

function dayLabel(iso: string) {
  const d = new Date(iso), now = new Date();
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  const yest = new Date(now); yest.setDate(now.getDate() - 1);
  if (same(d, now)) return "Today";
  if (same(d, yest)) return "Yesterday";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function tstamp(iso: string) {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}
