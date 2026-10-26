"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { CompanyWizard } from "@/components/CompanyWizard";
import { Chip, ErrorBox, Loading, PageHead, useAction } from "@/components/ui";
import { api, currentTenant, setTenant } from "@/lib/api";
import { roleList } from "@/lib/format";
import { clearCache, useApi } from "@/lib/useApi";
import { useSession } from "@/lib/session";

/** Every business the caller created or belongs to — any role, any workspace. */
export default function Businesses() {
  const router = useRouter();
  const { switchTenant, refresh } = useSession();
  const { run } = useAction();
  const { data, error, loading, reload } = useApi<any[]>("/my/businesses");
  const [creating, setCreating] = useState(false);
  const [resuming, setResuming] = useState<any>(null);

  const open = async (b: any) => {
    const cid = b.company_id ?? b.id;
    const tid = b.tenant_id ?? currentTenant();
    if (!cid || !tid) {
      await run(async () => { throw new Error("The new business has no ID to open — reload the list and try again."); });
      return;
    }
    if (tid !== currentTenant()) {
      await switchTenant(tid);
      clearCache();
    }
    router.push(`/companies/${cid}`);
  };

  const resume = async (b: any) => {
    // Continue inside the draft's own account: the wizard then adds a session
    // to it (never a second account) and completing it submits the company.
    if (b.tenant_id !== currentTenant()) {
      await switchTenant(b.tenant_id);
      clearCache();
    }
    setResuming(b);
  };

  const discard = async (b: any) => {
    if (!window.confirm("Throw away this unfinished company setup? This can't be undone.")) return;
    await run(async () => {
      await api(`/onboarding/accounts/${b.tenant_id}`, { method: "DELETE" });
      if (currentTenant() === b.tenant_id) setTenant(null);
      clearCache();
      await reload();
      await refresh();
    }, "Draft discarded");
  };

  if (loading) return <Loading rows={6} />;
  return (
    <>
      <PageHead title="My companies" sub="Every company you created or belong to. A new company is reviewed and activated by the myTrakIn team."
        actions={<button className="btn pri" onClick={() => setCreating(true)}>Create your company</button>} />
      <ErrorBox error={error} retry={reload} />
      {!data?.length ? <p className="muted">No companies yet. Create your company to get started — companies you're invited to appear here too.</p> : (
        <div className="grid c2">
          {data.map((b: any) => (b.kind === "draft" || !b.company_id ? (
            <div key={`${b.tenant_id}:draft`} className="card">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <b>Unfinished company setup</b>
                <Chip status="draft" />
              </div>
              <div className="muted" style={{ fontSize: 12.5 }}>Started but never submitted — it
                doesn&apos;t count as a company yet and isn&apos;t sent for activation.</div>
              <div className="row mt">
                <button className="btn sm pri" onClick={() => resume(b)}>Resume setup</button>
                <button className="btn sm" onClick={() => discard(b)}>Discard draft</button>
              </div>
            </div>
          ) : (
            <div key={`${b.tenant_id}:${b.company_id}`} className="card click" onClick={() => open(b)}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <b className="row" style={{ gap: 8, alignItems: "center", minWidth: 0 }}>
                  {b.logo_url && <img src={b.logo_url} alt="" style={{ height: 26, maxWidth: 80, objectFit: "contain", borderRadius: 6 }} />}
                  {b.company_name}
                </b><code>{b.business_code}</code>
              </div>
              <div className="muted" style={{ fontSize: 12.5 }}>{b.tenant_name} · {roleList(b)}</div>
              <div className="row mt">
                <Chip status={b.company_role ?? b.tenant_role ?? "member"} />
                <Chip status={b.tenant_status === "rejected" ? "rejected" : b.status} />
              </div>
              {b.tenant_status === "rejected" && (
                <p className="err" style={{ fontSize: 12.5, marginBottom: 0 }}>
                  Rejected by the myTrakIn team{b.decision_note ? `: “${b.decision_note}”` : ""}. Open it to fix the details and resubmit.
                </p>
              )}
            </div>
          )))}
        </div>
      )}
      {creating && <CompanyWizard account onClose={() => { setCreating(false); reload(); refresh(); }}
        onDone={async (c) => { await refresh(); open(c); }} />}
      {resuming && <CompanyWizard key={resuming.tenant_id} resumeId={resuming.session_id} onClose={() => { setResuming(null); reload(); refresh(); }}
        onDone={async (c) => { setResuming(null); await refresh(); open(c); }} />}
    </>
  );
}
