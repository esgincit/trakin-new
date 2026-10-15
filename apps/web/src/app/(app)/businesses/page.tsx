"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { CompanyWizard } from "@/components/CompanyWizard";
import { Chip, ErrorBox, Loading, PageHead, useAction } from "@/components/ui";
import { currentTenant } from "@/lib/api";
import { clearCache, useApi } from "@/lib/useApi";
import { useSession } from "@/lib/session";

/** Every business the caller created or belongs to — any role, any workspace. */
export default function Businesses() {
  const router = useRouter();
  const { switchTenant, refresh } = useSession();
  const { run } = useAction();
  const { data, error, loading, reload } = useApi<any[]>("/my/businesses");
  const [creating, setCreating] = useState(false);

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

  if (loading) return <Loading rows={6} />;
  return (
    <>
      <PageHead title="My companies" sub="Every company you created or belong to. A new company is reviewed and activated by the myTrakIn team."
        actions={<button className="btn pri" onClick={() => setCreating(true)}>Create your company</button>} />
      <ErrorBox error={error} retry={reload} />
      {!data?.length ? <p className="muted">No companies yet. Create your company to get started — companies you're invited to appear here too.</p> : (
        <div className="grid c2">
          {data.map((b: any) => (
            <div key={`${b.tenant_id}:${b.company_id}`} className="card click" onClick={() => open(b)}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <b>{b.company_name}</b><code>{b.business_code}</code>
              </div>
              <div className="muted" style={{ fontSize: 12.5 }}>{b.tenant_name} · {b.kind.replace(/_/g, " ")}</div>
              <div className="row mt">
                <Chip status={b.company_role ?? b.tenant_role ?? "member"} />
                <Chip status={b.status} />
              </div>
            </div>
          )          )}
        </div>
      )}
      {creating && <CompanyWizard account onClose={() => { setCreating(false); reload(); refresh(); }}
        onDone={async (c) => { await refresh(); open(c); }} />}
    </>
  );
}
