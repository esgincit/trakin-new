"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { PageHead, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { uploadDirect } from "@/lib/upload";

type Admin = { name: string; email: string; company: string | null; company_id: string; company_role: string };
type Creator = { name: string; email: string; company: string | null; company_id: string | null };
type Parties = {
  creator: Creator;
  counterparty: { id: string; name: string | null } | null;
  signers: Admin[];
};

/** A counterparty signer row: either one of their admins, or an e-mail we were asked to invite. */
type Signer =
  | { kind: "admin"; email: string; name: string; company: string | null; company_id: string | null }
  | { kind: "invite"; email: string; name: string };

export default function NewEnvelopePage() {
  return <Suspense><NewEnvelope /></Suspense>;
}

function NewEnvelope() {
  const params = useSearchParams();
  const router = useRouter();
  const agreementId = params.get("agreement_id") ?? "";
  const [title, setTitle] = useState(params.get("title") ?? "");
  const [files, setFiles] = useState<File[]>([]);
  const [sequential, setSequential] = useState(true);
  const [note, setNote] = useState("");
  const [parties, setParties] = useState<Parties | null>(null);
  const [signers, setSigners] = useState<Signer[]>([]);
  const { run, busy } = useAction();

  // Who is expected to sign: us (fixed, first) and the other company's admins.
  useEffect(() => {
    let live = true;
    api<Parties>("/envelopes/signing-parties", {
      query: { agreement_id: agreementId, sow_id: params.get("sow_id"), amendment_id: params.get("amendment_id") },
    })
      .then((p) => {
        if (!live) return;
        setParties(p);
        // The counterparty's strongest admin is offered as the default signer.
        setSigners(p.signers.length ? [{ kind: "admin", ...p.signers[0] }] : []);
      })
      .catch(() => live && setParties(null));
    return () => { live = false; };
  }, [agreementId, params]);

  const update = (i: number, patch: Partial<Signer>) =>
    setSigners((s) => s.map((x, j) => (j === i ? ({ ...x, ...patch } as Signer) : x)));

  const submit = async (send: boolean) => {
    if (!files.length) return alert("Choose at least one PDF to sign");
    if (!parties?.creator) return alert("Could not work out who signs — reload and try again");
    const people = [
      { name: parties.creator.name, email: parties.creator.email, company: parties.creator.company, company_id: parties.creator.company_id },
      ...signers.map((s) => ({ name: s.name, email: s.email, company: parties.counterparty?.name ?? null })),
    ].filter((p) => p.name && p.email);
    const emails = people.map((p) => p.email.toLowerCase());
    if (new Set(emails).size !== emails.length) return alert("Each signer needs a different e-mail address");

    const form = new FormData();
    form.set("title", title);
    form.set("signers", JSON.stringify(people));
    form.set("message", note);            // stored as the envelope's note; label only changed
    form.set("sequential", String(sequential));
    for (const k of ["agreement_id", "sow_id", "amendment_id", "consultant_id"]) {
      const v = params.get(k);
      if (v) form.set(k, v);
    }
    const env = await run(async () => {
      // Every document is uploaded on its own first. A packet of ten PDFs in one
      // request would be far past the request-body limit, and this keeps the order
      // the user chose.
      const paths: string[] = [];
      for (const f of files) paths.push(await uploadDirect(f, { purpose: "esign" }));
      form.set("document_paths", JSON.stringify(paths));
      const created = await api("/envelopes", { form });
      if (send) await api(`/envelopes/${created.id}/send`, { method: "POST" });
      return created;
    }, send ? "Sent — the first signer has the link" : "Saved as draft");
    if (env) router.push(`/esign/${env.id}`);
  };

  const admins = parties?.signers ?? [];
  const noAdmins = parties && admins.length === 0;

  return (
    <>
      <PageHead title="Send a document for signature" sub="Signers confirm their e-mail with a one-time code, agree to sign electronically, then sign. You get a sealed PDF with a certificate of completion." />
      <div className="card form" style={{ maxWidth: 760 }}>
        <label htmlFor="t">Title</label>
        <input id="t" className="ctl" value={title} onChange={(e) => setTitle(e.target.value)} required placeholder="Master Services Agreement — Nova Analytics" />

        <label htmlFor="f">Documents (up to 10)</label>
        {files.map((f, i) => (
          <div key={`${f.name}-${i}`} className="row" style={{ marginBottom: 6 }}>
            <input
              className="ctl"
              type="file"
              accept="application/pdf"
              aria-label={`Replace ${f.name}`}
              onChange={(e) => {
                const next = e.target.files?.[0];
                if (next) setFiles((x) => x.map((old, j) => (j === i ? next : old)));
              }}
              style={{ flex: 1 }}
            />
            {files.length > 1 && (
              <button className="btn sm" type="button" onClick={() => setFiles((x) => x.filter((_, j) => j !== i))} aria-label={`Remove ${f.name}`}>✕</button>
            )}
          </div>
        ))}
        {files.length < 10 && (
          <input
            id="f"
            className="ctl"
            type="file"
            accept="application/pdf"
            onChange={(e) => {
              const next = e.target.files?.[0];
              if (next) setFiles((x) => [...x, next]);
              e.target.value = "";
            }}
          />
        )}
        <p className="note" style={{ marginTop: -6 }}>
          {files.length > 1
            ? `${files.length} documents. Every signer gets them in this order, followed by one certificate of completion.`
            : "Add an MSA and its SOW, or a contract and its exhibits — one envelope, signed once."}
        </p>

        <label>Signers, in signing order</label>
        <div className="row" style={{ marginBottom: 6 }}>
          <b style={{ width: 18 }}>1.</b>
          <div className="ctl" style={{ flex: 1, background: "var(--panel-2, transparent)" }}>
            You — {parties?.creator?.name ?? "…"}{parties?.creator?.company ? ` (${parties.creator.company})` : ""}
          </div>
          <span className="note" style={{ width: 120 }}>your company</span>
        </div>

        {signers.map((s, i) => (
          <div key={i} className="row" style={{ marginBottom: 6 }}>
            <b style={{ width: 18 }}>{i + 2}.</b>
            {s.kind === "admin" && admins.length > 0 ? (
              <>
                <select
                  className="ctl"
                  aria-label={`Signer ${i + 2}`}
                  value={s.email}
                  onChange={(e) => {
                    const chosen = admins.find((a) => a.email === e.target.value);
                    if (chosen) update(i, { kind: "admin", ...chosen });
                  }}
                  style={{ flex: 1 }}
                >
                  {admins.map((a) => (
                    <option key={a.email} value={a.email}>
                      {a.name} — {a.company_role.replace("_", " ")}
                    </option>
                  ))}
                </select>
                <span className="note" style={{ width: 120 }}>{parties?.counterparty?.name}</span>
              </>
            ) : (
              <>
                <input
                  className="ctl"
                  placeholder="Full name"
                  aria-label={`Signer ${i + 2} name`}
                  value={s.name}
                  onChange={(e) => update(i, { name: e.target.value })}
                  style={{ flex: 1 }}
                />
                <input
                  className="ctl"
                  type="email"
                  placeholder="E-mail"
                  aria-label={`Signer ${i + 2} e-mail`}
                  value={s.email}
                  onChange={(e) => update(i, { email: e.target.value })}
                  style={{ flex: 1 }}
                />
              </>
            )}
            <button className="btn sm" type="button" onClick={() => setSigners((x) => x.filter((_, j) => j !== i))} aria-label={`Remove signer ${i + 2}`}>✕</button>
          </div>
        ))}

        {noAdmins && (
          <p className="note" style={{ marginTop: -6 }}>
            {parties?.counterparty?.name ?? "The other company"} has no admin with an account yet, so add the
            signer by e-mail — they can sign without one, and you will be told when they are set up.
          </p>
        )}
        <button
          className="btn sm"
          type="button"
          onClick={() =>
            setSigners((s) => {
              const used = new Set(s.filter((x) => x.kind === "admin").map((x) => x.email));
              const next = admins.find((a) => !used.has(a.email));
              return next
                ? [...s, { kind: "admin", ...next }]
                : [...s, { kind: "invite", email: "", name: "" }];
            })
          }
        >
          Add signer
        </button>

        <label className="row" style={{ color: "var(--ink)" }}>
          <input type="checkbox" className="toggle" checked={sequential} onChange={(e) => setSequential(e.target.checked)} />
          Sign in order (each signer gets the link after the previous one signs)
        </label>
        <label htmlFor="m">Note</label>
        <textarea id="m" className="ctl" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Please review and sign by Friday." />
        <p className="note" style={{ marginTop: -6 }}>
          Shown to the signers and to the other company&apos;s admins, who are notified when you send.
        </p>

        <div className="row mt">
          <button className="btn" disabled={busy} onClick={() => submit(false)}>Save draft</button>
          <button className="btn pri" disabled={busy} onClick={() => submit(true)}>Send now</button>
        </div>
        <p className="note">Reminders go out automatically every 3 days. Links expire after 30 days.</p>
      </div>
    </>
  );
}