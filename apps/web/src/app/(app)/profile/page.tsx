"use client";

import { useRef, useState } from "react";
import { ProfileView } from "@/components/ProfileView";
import { ErrorBox, Field, formValues, Loading, PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

/** My LinkedIn-style profile: photo, cover, headline, about, experience, skills — and who can see it. */
export default function MyProfile() {
  const { data: p, error, loading, reload } = useApi("/network/me");
  const [editing, setEditing] = useState(false);
  const photo = useRef<HTMLInputElement>(null);
  const cover = useRef<HTMLInputElement>(null);
  const { run, busy } = useAction();
  const { refresh } = useSession();
  const [experience, setExperience] = useState<any[] | null>(null);

  if (loading) return <Loading rows={6} />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  const exp = experience ?? p.experience ?? [];

  const upload = async (kind: "avatar" | "cover", file?: File) => {
    if (!file) return;
    const form = new FormData();
    form.set("file", file);
    if (await run(() => api("/network/me/photo", { form, query: { kind } }), kind === "avatar" ? "Photo updated" : "Cover updated")) { reload(); refresh(); }
  };

  const remove = async (kind: "avatar" | "cover") => {
    if (await run(() => api("/network/me/photo", { method: "DELETE", query: { kind } }), kind === "avatar" ? "Photo removed" : "Cover removed")) { reload(); refresh(); }
  };

  return (
    <>
      <PageHead title="My profile" sub="Your profile belongs to you and moves with you between companies." actions={<>
        <input ref={photo} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => upload("avatar", e.target.files?.[0])} />
        <input ref={cover} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => upload("cover", e.target.files?.[0])} />
        <button className="btn" onClick={() => photo.current?.click()}>Change photo</button>
        <button className="btn" onClick={() => cover.current?.click()}>Change cover</button>
        {p.avatar_url && <button className="btn" disabled={busy} onClick={() => remove("avatar")}>Remove photo</button>}
        {p.cover_url && <button className="btn" disabled={busy} onClick={() => remove("cover")}>Remove cover</button>}
        <button className="btn pri" onClick={() => { setEditing((x) => !x); setExperience(null); }}>{editing ? "Close editor" : "Edit profile"}</button>
      </>} />
      {editing ? (
        <form className="card form" onSubmit={async (e) => {
          e.preventDefault();
          const v: any = formValues(e.currentTarget);
          const body: any = {
            full_name: v.full_name, headline: v.headline ?? null, location: v.location ?? null, about: v.about ?? null, phone: v.phone ?? null,
            website: v.website ?? null, visibility: v.visibility, open_to_work: v.open_to_work === "yes", show_contact: v.show_contact === "yes",
            skills: (v.skills ?? "").split(",").map((s: string) => s.trim()).filter(Boolean),
            experience: exp.filter((x: any) => x.title && x.company),
          };
          if (await run(() => api("/network/me", { method: "PATCH", body }), "Profile saved")) { setEditing(false); reload(); }
        }}>
          <div className="fields">
            <Field label="Full name" name="full_name" defaultValue={p.full_name ?? ""} required />
            <Field label="Headline" name="headline" defaultValue={p.headline ?? ""} placeholder="SAP GRC Consultant · S/4HANA Security" />
            <Field label="Location" name="location" defaultValue={p.location ?? ""} />
            <Field label="Website" name="website" type="url" defaultValue={p.website ?? ""} />
            <Field label="Phone" name="phone" defaultValue={p.phone ?? ""} />
            <Field label="Open to work" name="open_to_work" as="select" defaultValue={p.open_to_work ? "yes" : "no"} options={[["no", "No"], ["yes", "Yes"]]} />
            <Field label="Who can see my profile" name="visibility" as="select" defaultValue={p.visibility} options={[["network", "Everyone on myTrakIn"], ["company_and_connections", "My companies and connections"], ["company", "Only people at my companies"]]} />
            <Field label="Show e-mail and phone to connections" name="show_contact" as="select" defaultValue={p.show_contact ? "yes" : "no"} options={[["yes", "Yes"], ["no", "No"]]} />
            <Field label="About" name="about" as="textarea" defaultValue={p.about ?? ""} full />
            <Field label="Skills (comma separated)" name="skills" defaultValue={(p.skills ?? []).join(", ")} full />
          </div>
          <h3 className="mt">Experience</h3>
          {exp.map((x: any, i: number) => (
            <div key={i} className="row" style={{ marginBottom: 6 }}>
              {(["title", "company", "start", "end"] as const).map((k) => (
                <input key={k} className="ctl" placeholder={k === "end" ? "end (blank = present)" : k} value={x[k] ?? ""} style={{ flex: k === "title" || k === "company" ? 2 : 1 }}
                       onChange={(e) => setExperience(exp.map((y: any, j: number) => (j === i ? { ...y, [k]: e.target.value || null } : y)))} aria-label={k} />
              ))}
              <button type="button" className="btn sm" onClick={() => setExperience(exp.filter((_: any, j: number) => j !== i))} aria-label="Remove">✕</button>
            </div>
          ))}
          <button type="button" className="btn sm" onClick={() => setExperience([...exp, { title: "", company: "", start: "", end: null }])}>Add position</button>
          <div><button className="btn pri mt" disabled={busy}>Save profile</button></div>
        </form>
      ) : <ProfileView p={p} />}
    </>
  );
}
