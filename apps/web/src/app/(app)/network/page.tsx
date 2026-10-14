"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { Avatar, Chip, Empty, ErrorBox, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { allows, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

type Tab = "feed" | "people" | "connections" | "messages";

export default function NetworkPage() {
  return <Suspense><Network /></Suspense>;
}

function Network() {
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) ?? "feed");
  return (
    <>
      <PageHead title="Network" sub="Your professional profile, colleagues across companies you work with, updates and messages." actions={<Link className="btn" href="/profile">My profile</Link>} />
      <div className="tabs">
        {(["feed", "people", "connections", "messages"] as Tab[]).map((t) => <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{t[0]!.toUpperCase() + t.slice(1)}</button>)}
      </div>
      {tab === "feed" && <Feed />}
      {tab === "people" && <People />}
      {tab === "connections" && <Connections />}
      {tab === "messages" && <Messages initial={params.get("with")} />}
    </>
  );
}

function Feed() {
  const { workspace, me } = useSession();
  const { data, error, reload } = useApi<any[]>("/network/feed");
  const [body, setBody] = useState("");
  const [kind, setKind] = useState("update");
  const [audience, setAudience] = useState(workspace ? "company" : "network");
  const { run, busy } = useAction();
  return (
    <div className="grid c2">
      <div className="card">
        {!workspace && (
          <p className="muted" style={{ marginTop: 0 }}>
            <b>Welcome!</b> You can post, connect and message right away. To use payments, timesheets and contracts, ask your
            administrator to invite <b>{me?.profile?.email}</b>, or <Link href="/signup">request a workspace</Link> for your company.
            Tip: add two-step verification under <Link href="/account">Account & security</Link>.
          </p>
        )}
        <form onSubmit={async (e) => { e.preventDefault(); if (await run(() => api("/network/posts", { body: { body, kind, audience } }), "Posted")) { setBody(""); reload(); } }}>
          <textarea className="ctl" placeholder="Share an update, thank a colleague, or post an opening…" value={body} onChange={(e) => setBody(e.target.value)} maxLength={3000} />
          <div className="row mt">
            <select className="ctl" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Post type">
              <option value="update">Update</option><option value="kudos">Kudos</option><option value="opening">Job opening</option>
              {allows(workspace, "hr") && <option value="announcement">Announcement</option>}
            </select>
            <select className="ctl" value={audience} onChange={(e) => setAudience(e.target.value)} aria-label="Audience">
              {workspace && <option value="company">{workspace.tenant.name} only</option>}<option value="network">Everyone in my network</option>
            </select>
            <button className="btn pri right" disabled={busy || !body.trim()}>Post</button>
          </div>
        </form>
        <ErrorBox error={error} retry={reload} />
        {data?.map((p) => (
          <div key={p.id} className="post">
            <Avatar name={p.author} url={p.avatar_url} size={40} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <Link href={`/network/${p.author_id}`}><b>{p.author}</b></Link> {p.kind !== "update" && <Chip status={p.kind === "announcement" ? "pending" : "open"}>{p.kind}</Chip>}
              <div className="meta">{p.headline} · {dateTime(p.created_at)}{p.network_wide && " · network"}</div>
              <p style={{ whiteSpace: "pre-wrap", margin: "8px 0 0" }}>{p.body}</p>
              <div className="acts">
                <button onClick={async () => { await run(() => api(`/network/posts/${p.id}/like`, { method: "POST" })); reload(); }}>👍 {p.likes}</button>
                {p.mine && <button onClick={async () => { if (confirm("Delete this post?")) { await run(() => api(`/network/posts/${p.id}`, { method: "DELETE" }), "Deleted"); reload(); } }}>Delete</button>}
              </div>
            </div>
          </div>
        ))}
        {data && !data.length && <Empty>No posts yet. Be the first to share an update.</Empty>}
      </div>
      <Connections compact />
    </div>
  );
}

function People() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [otw, setOtw] = useState(false);
  const { data } = useApi<any[]>("/network/people", { q: q || undefined, open_to_work: otw || undefined });
  const { run } = useAction();
  return (
    <>
      <div className="toolbar">
        <input className="ctl" type="search" placeholder="Name, skill, title or city" value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="row" style={{ margin: 0 }}><input type="checkbox" className="toggle" checked={otw} onChange={(e) => setOtw(e.target.checked)} /> Open to work</label>
      </div>
      <div className="cgrid">
        {data?.map((p) => (
          <div key={p.id} className="ccard click" onClick={() => router.push(`/network/${p.id}`)}>
            <div className="ch"><Avatar name={p.full_name} url={p.avatar_url} size={48} /><div><b>{p.full_name}</b><div className="muted" style={{ fontSize: 12.5 }}>{p.headline}</div></div></div>
            <div className="muted" style={{ fontSize: 12.5 }}>{p.location}</div>
            <div className="row mt" style={{ gap: 4 }}>{(p.skills ?? []).slice(0, 4).map((s: string) => <span key={s} className="chip">{s}</span>)}</div>
            <div className="row mt">
              {p.open_to_work && <Chip status="ok">Open to work</Chip>}
              <span className="right" />
              {!p.connection && <button className="btn sm" onClick={async (e) => { e.stopPropagation(); await run(() => api(`/network/connections/${p.id}`, { method: "POST" }), "Invitation sent"); }}>Connect</button>}
              {p.connection && <Chip status={p.connection === "accepted" ? "accepted" : "pending"}>{p.connection === "accepted" ? "Connected" : "Pending"}</Chip>}
            </div>
          </div>
        ))}
      </div>
      {data && !data.length && <Empty>No one matches.</Empty>}
    </>
  );
}

function Connections({ compact }: { compact?: boolean }) {
  const { data, reload } = useApi("/network/connections");
  const { run } = useAction();
  if (!data) return <div className="card"><div className="skel" /></div>;
  return (
    <div className="card">
      {data.incoming.length > 0 && <>
        <h3>Invitations</h3>
        {data.incoming.map((p: any) => (
          <div key={p.id} className="alert">
            <Avatar name={p.full_name} url={p.avatar_url} /><div style={{ flex: 1 }}><Link href={`/network/${p.id}`}>{p.full_name}</Link><div className="muted" style={{ fontSize: 12.5 }}>{p.headline}</div></div>
            <button className="btn sm pri" onClick={async () => { await run(() => api(`/network/connections/${p.id}/respond`, { method: "POST", query: { accept: true } }), "Connected"); reload(); }}>Accept</button>
            <button className="btn sm" onClick={async () => { await run(() => api(`/network/connections/${p.id}/respond`, { method: "POST", query: { accept: false } })); reload(); }}>Ignore</button>
          </div>
        ))}
      </>}
      <h3>Connections ({data.connections.length})</h3>
      {data.connections.slice(0, compact ? 8 : undefined).map((p: any) => (
        <div key={p.id} className="alert"><Avatar name={p.full_name} url={p.avatar_url} /><div style={{ flex: 1 }}><Link href={`/network/${p.id}`}>{p.full_name}</Link><div className="muted" style={{ fontSize: 12.5 }}>{p.headline}</div></div>
          {!compact && <Link className="btn sm" href={`/network?tab=messages&with=${p.id}`}>Message</Link>}</div>
      ))}
      {!data.connections.length && <p className="muted">Connect with colleagues, consultants and partners from the People tab.</p>}
      {!compact && data.outgoing.length > 0 && <p className="note">{data.outgoing.length} invitation(s) waiting for a reply.</p>}
    </div>
  );
}

function Messages({ initial }: { initial: string | null }) {
  const threads = useApi<any[]>("/network/messages");
  const [withId, setWithId] = useState<string | null>(initial);
  const convo = useApi<any[]>(withId ? `/network/messages/${withId}` : null);
  const person = useApi(withId && !threads.data?.some((t) => t.person_id === withId) ? `/network/people/${withId}` : null);
  const [text, setText] = useState("");
  const { run, busy } = useAction();
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [convo.data]);
  useEffect(() => {
    if (!withId) return;
    const t = setInterval(convo.reload, 15000);   // light polling while a conversation is open
    return () => clearInterval(t);
  }, [withId, convo.reload]);
  const current = threads.data?.find((t) => t.person_id === withId) ?? person.data;

  return (
    <div className="msgs">
      <div className="list">
        {threads.data?.map((t) => (
          <a key={t.person_id} className={t.person_id === withId ? "on" : ""} onClick={() => setWithId(t.person_id)}>
            <div className="row"><Avatar name={t.full_name} url={t.avatar_url} size={28} /><b style={{ flex: 1 }}>{t.full_name}</b>{t.unread > 0 && <span className="nb">{t.unread}</span>}</div>
            <div className="muted" style={{ fontSize: 12.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.last_message}</div>
          </a>
        ))}
        {threads.data && !threads.data.length && <p className="muted" style={{ padding: 12 }}>No messages yet.</p>}
      </div>
      <div className="thread">
        {withId ? (
          <>
            <div style={{ padding: 12, borderBottom: "1px solid var(--line)" }}><b>{current?.full_name ?? "…"}</b></div>
            <div className="body">
              {convo.data?.map((m) => <div key={m.id} className={`bub ${m.mine ? "me" : ""}`}>{m.body}<small>{dateTime(m.created_at)}</small></div>)}
              <div ref={end} />
            </div>
            <form className="row" style={{ padding: 10, borderTop: "1px solid var(--line)" }} onSubmit={async (e) => {
              e.preventDefault();
              if (await run(() => api(`/network/messages/${withId}`, { body: { body: text } }))) { setText(""); convo.reload(); threads.reload(); }
            }}>
              <input className="ctl" style={{ flex: 1 }} value={text} onChange={(e) => setText(e.target.value)} placeholder="Write a message…" aria-label="Message" />
              <button className="btn pri" disabled={busy || !text.trim()}>Send</button>
            </form>
          </>
        ) : <Empty>Choose a conversation, or message someone from their profile.</Empty>}
      </div>
    </div>
  );
}
