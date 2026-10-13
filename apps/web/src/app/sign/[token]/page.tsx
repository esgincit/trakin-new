"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { SignaturePad } from "@/components/SignaturePad";
import { Chip } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { dateTime } from "@/lib/format";

/** The public signing page. No account needed: the link plus a one-time e-mail code identify the signer. */
export default function SignPage() {
  const { token } = useParams<{ token: string }>();
  const base = `/public/sign/${token}`;
  const [view, setView] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [pdf, setPdf] = useState<string | null>(null);
  const [mode, setMode] = useState<"typed" | "drawn">("typed");
  const [typed, setTyped] = useState("");
  const [drawn, setDrawn] = useState<string | null>(null);
  const [agree, setAgree] = useState(false);
  const [consent, setConsent] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const v = await api(base, { auth: false });
      setView(v);
      setTyped(v.signer.name);
    } catch (e) {
      setError((e as ApiError).message);
    }
  }, [base]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!view?.signer.verified || pdf) return;
    api<Response>(`${base}/document`, { auth: false, raw: true }).then(async (r) => {
      // Hosted: a short-lived link straight to storage. Local development: the PDF itself.
      if (r.headers.get("content-type")?.includes("application/json")) setPdf((await r.json()).url);
      else setPdf(URL.createObjectURL(await r.blob()));
    }).catch(() => {});
  }, [view, base, pdf]);

  const step = async (fn: () => Promise<any>) => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  if (done) return <Shell><h2>Thank you</h2><p>{done}</p><p className="muted">You can close this window.</p></Shell>;
  if (!view) return <Shell>{error ? <><h2>This link doesn't work</h2><p className="muted">{error}</p></> : <div className="skel" />}</Shell>;

  const { envelope, signer } = view;
  const closed = envelope.status !== "sent" || ["signed", "declined"].includes(signer.status);

  return (
    <Shell wide>
      <div className="row"><h2 style={{ flex: 1 }}>{envelope.title}</h2><Chip status={closed ? envelope.status : signer.status} /></div>
      <p className="muted">From {envelope.sent_by} · {envelope.number}{envelope.expires_at && ` · link valid until ${dateTime(envelope.expires_at)}`}</p>
      {envelope.message && <p>{envelope.message}</p>}
      <div className="row" style={{ gap: 6, marginBottom: 12 }}>
        {view.signers.map((s: any) => <span key={s.position} className="person">{s.position}. {s.name} <Chip status={s.status} /></span>)}
      </div>

      {closed ? (
        <p className="muted">{signer.status === "signed" ? "You have signed this document. We'll e-mail the completed copy when everyone has signed." : `This envelope is ${envelope.status}.`}</p>
      ) : !view.my_turn ? (
        <p className="muted">It isn't your turn yet. We'll e-mail you when the earlier signers are done.</p>
      ) : !signer.verified ? (
        <div className="card">
          <h3>1. Confirm it's you</h3>
          <p className="muted">We'll e-mail a 6-digit code to {signer.email}.</p>
          {info && <p className="ok">{info}</p>}
          <div className="row">
            <button className="btn" disabled={busy} onClick={() => step(async () => { const r = await api(`${base}/code`, { method: "POST", auth: false }); setInfo(`Code sent to ${r.sent_to}`); })}>Send code</button>
            <input className="ctl" inputMode="numeric" maxLength={6} placeholder="123456" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} aria-label="6-digit code" style={{ width: 120, letterSpacing: 4 }} />
            <button className="btn pri" disabled={busy || code.length !== 6} onClick={() => step(async () => { await api(`${base}/verify`, { body: { code }, auth: false }); await load(); })}>Verify</button>
          </div>
        </div>
      ) : !signer.consented ? (
        <div className="card">
          <h3>2. Agree to sign electronically</h3>
          <p className="note" style={{ fontSize: 13.5 }}>{view.disclosure}</p>
          <label className="row" style={{ color: "var(--ink)" }}><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> I agree to use electronic records and signatures.</label>
          <button className="btn pri mt" disabled={busy || !consent} onClick={() => step(async () => { await api(`${base}/consent`, { method: "POST", auth: false }); await load(); })}>Continue</button>
        </div>
      ) : (
        <>
          {pdf ? <iframe className="pdf" src={pdf} title="Document to sign" /> : <div className="skel" style={{ height: 300 }} />}
          {pdf && <p className="note"><a href={pdf} target="_blank" rel="noopener">Open the document in a new tab</a> (easier on phones)</p>}
          <div className="card mt">
            <h3>3. Sign</h3>
            <div className="seg">
              <button className={mode === "typed" ? "on" : ""} onClick={() => setMode("typed")}>Type</button>
              <button className={mode === "drawn" ? "on" : ""} onClick={() => setMode("drawn")}>Draw</button>
            </div>
            {mode === "typed" ? (
              <>
                <input className="ctl mt" value={typed} onChange={(e) => setTyped(e.target.value)} aria-label="Type your full name" style={{ width: "100%" }} />
                <div className="sigtyped mt" aria-hidden="true">{typed}</div>
              </>
            ) : <div className="mt"><SignaturePad onChange={setDrawn} /></div>}
            <label className="row mt" style={{ color: "var(--ink)" }}><input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
              I have reviewed this document and intend to sign it. My signature, the time, my IP address ({view.your_ip}) and device will be recorded.</label>
            <div className="row mt">
              <button className="btn pri" disabled={busy || !agree || (mode === "typed" ? typed.trim().length < 2 : !drawn)} onClick={() => step(async () => {
                const r = await api(`${base}/sign`, { body: { signature_type: mode, signature_data: mode === "typed" ? typed.trim() : drawn, agree }, auth: false });
                setDone(r.message);
              })}>Sign</button>
              <span style={{ flex: 1 }} />
              <button className="btn" disabled={busy} onClick={() => {
                const reason = prompt("Tell the sender why you're declining:");
                if (reason) step(async () => { await api(`${base}/decline`, { body: { reason }, auth: false }); setDone("You declined to sign. The sender has been told."); });
              }}>Decline</button>
            </div>
          </div>
        </>
      )}
      {error && <p className="err" role="alert">{error}</p>}
    </Shell>
  );
}

function Shell({ children, wide }: { children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="auth" style={wide ? { maxWidth: 900 } : undefined}>
      <div className="logo" style={{ justifyContent: "center", fontSize: 18 }}><i>mT</i>myTrakIn e-signature</div>
      <div className="card">{children}</div>
      <p className="muted" style={{ textAlign: "center", fontSize: 12.5 }}>Secured by myTrakIn · Your link is personal; please don't forward it.</p>
    </div>
  );
}
