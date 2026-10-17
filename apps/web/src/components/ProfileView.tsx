"use client";

import type { ReactNode } from "react";
import { Avatar, Chip } from "./ui";

export function ProfileView({ p, actions }: { p: any; actions?: ReactNode }) {
  return (
    <div className="pgrid">
      <div>
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <div className="cover" style={p.cover_url ? { backgroundImage: `url(${p.cover_url})` } : undefined} />
          <div style={{ padding: "0 20px 20px" }}>
            {p.avatar_url ? <img className="bigav" src={p.avatar_url} alt="" /> : <div className="bigav">{(p.full_name ?? "?").split(" ").map((x: string) => x[0]).slice(0, 2).join("")}</div>}
            <h1 style={{ marginTop: 8 }}>{p.full_name}</h1>
            {p.user_code && <div className="muted" style={{ fontSize: 12.5 }}>ID <code>{p.user_code}</code></div>}
            <div>{p.headline}</div>
            <div className="muted">{p.location}{p.connections != null && ` · ${p.connections} connections`}</div>
            {p.open_to_work && <Chip status="ok">Open to work</Chip>}
            <div className="row mt">{actions}</div>
          </div>
        </div>
        {p.about && <div className="card mt"><h3>About</h3><p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{p.about}</p></div>}
        {p.experience?.length > 0 && <div className="card mt"><h3>Experience</h3>{p.experience.map((x: any, i: number) => (
          <div key={i} className="alert"><Avatar name={x.company} /><div><b>{x.title}</b><div>{x.company}</div><div className="muted" style={{ fontSize: 12.5 }}>{x.start} – {x.end ?? "present"}</div>{x.description && <p style={{ margin: "6px 0 0" }}>{x.description}</p>}</div></div>
        ))}</div>}
        {p.education?.length > 0 && <div className="card mt"><h3>Education</h3>{p.education.map((x: any, i: number) => <div key={i} className="alert"><div><b>{x.school}</b><div className="muted">{x.degree} {x.year && `· ${x.year}`}</div></div></div>)}</div>}
      </div>
      <div>
        <div className="card">
          <h3>Skills</h3>
          <div className="row" style={{ gap: 4 }}>{(p.skills ?? []).map((s: string) => <span key={s} className="chip">{s}</span>)}</div>
          {!p.skills?.length && <p className="muted">None listed.</p>}
        </div>
        {p.certifications?.length > 0 && <div className="card mt"><h3>Certifications</h3>{p.certifications.map((c: any, i: number) => <div key={i}><b>{c.name}</b> <span className="muted">{c.issuer} {c.year}</span></div>)}</div>}
        <div className="card mt">
          <h3>Contact</h3>
          {p.email ? <div><a href={`mailto:${p.email}`}>{p.email}</a></div> : <p className="muted">Shared after you connect.</p>}
          {p.phone && <div>{p.phone}</div>}
          {p.website && <div><a href={p.website} target="_blank" rel="noopener noreferrer">{p.website}</a></div>}
          {p.shared_workspaces?.length > 0 && <p className="note">Also at: {p.shared_workspaces.join(", ")}</p>}
        </div>
      </div>
    </div>
  );
}
