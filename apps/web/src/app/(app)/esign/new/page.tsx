"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { DIRECT_LIMIT, uploadDirect } from "@/lib/upload";

type Signer = { name: string; email: string; company: string };

export default function NewEnvelopePage() {
  return <Suspense><NewEnvelope /></Suspense>;
}

function NewEnvelope() {
  const params = useSearchParams();
  const router = useRouter();
  const [title, setTitle] = useState(params.get("title") ?? "");
  const [signers, setSigners] = useState<Signer[]>([{ name: "", email: "", company: "" }, { name: "", email: "", company: "" }]);
  const [file, setFile] = useState<File | null>(null);
  const [sequential, setSequential] = useState(true);
  const [message, setMessage] = useState("");
  const { run, busy } = useAction();

  const update = (i: number, k: keyof Signer, v: string) => setSigners((s) => s.map((x, j) => (j === i ? { ...x, [k]: v } : x)));

  const submit = async (send: boolean) => {
    if (!file) return alert("Choose the PDF to sign");
    const people = signers.filter((s) => s.name && s.email);
    if (!people.length) return alert("Add at least one signer");
    const form = new FormData();
    form.set("title", title);
    form.set("signers", JSON.stringify(people));
    form.set("message", message);
    form.set("sequential", String(sequential));
    for (const k of ["agreement_id", "sow_id", "amendment_id", "consultant_id"]) {
      const v = params.get(k);
      if (v) form.set(k, v);
    }
    const env = await run(async () => {
      if (file.size > DIRECT_LIMIT) form.set("document_path", await uploadDirect(file, { purpose: "esign" }));
      else form.set("file", file);
      const created = await api("/envelopes", { form });
      if (send) await api(`/envelopes/${created.id}/send`, { method: "POST" });
      return created;
    }, send ? "Sent — the first signer has the link" : "Saved as draft");
    if (env) router.push(`/esign/${env.id}`);
  };

  return (
    <>
      <PageHead title="Send a document for signature" sub="Signers confirm their e-mail with a one-time code, agree to sign electronically, then sign. You get a sealed PDF with a certificate of completion." />
      <div className="card form" style={{ maxWidth: 760 }}>
        <label htmlFor="t">Title</label>
        <input id="t" className="ctl" value={title} onChange={(e) => setTitle(e.target.value)} required placeholder="Master Services Agreement — Nova Analytics" />
        <label htmlFor="f">PDF (up to 25 MB)</label>
        <input id="f" className="ctl" type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <label>Signers, in signing order</label>
        {signers.map((s, i) => (
          <div key={i} className="row" style={{ marginBottom: 6 }}>
            <b style={{ width: 18 }}>{i + 1}.</b>
            <input className="ctl" placeholder="Full name" value={s.name} onChange={(e) => update(i, "name", e.target.value)} style={{ flex: 1 }} />
            <input className="ctl" type="email" placeholder="E-mail" value={s.email} onChange={(e) => update(i, "email", e.target.value)} style={{ flex: 1 }} />
            <input className="ctl" placeholder="Company" value={s.company} onChange={(e) => update(i, "company", e.target.value)} style={{ flex: 1 }} />
            {signers.length > 1 && <button className="btn sm" onClick={() => setSigners((x) => x.filter((_, j) => j !== i))} aria-label="Remove signer">✕</button>}
          </div>
        ))}
        <button className="btn sm" onClick={() => setSigners((s) => [...s, { name: "", email: "", company: "" }])}>Add signer</button>
        <label className="row" style={{ color: "var(--ink)" }}><input type="checkbox" className="toggle" checked={sequential} onChange={(e) => setSequential(e.target.checked)} /> Sign in order (each signer gets the link after the previous one signs)</label>
        <label htmlFor="m">Message to signers</label>
        <textarea id="m" className="ctl" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Please review and sign by Friday." />
        <div className="row mt">
          <button className="btn" disabled={busy} onClick={() => submit(false)}>Save draft</button>
          <button className="btn pri" disabled={busy} onClick={() => submit(true)}>Send now</button>
        </div>
        <p className="note">Reminders go out automatically every 3 days. Links expire after 30 days.</p>
      </div>
    </>
  );
}
