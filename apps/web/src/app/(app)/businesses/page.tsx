"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { CompanyWizard } from "@/components/CompanyWizard";
import { Chip, ErrorBox, Loading, PageHead } from "@/components/ui";
import { currentTenant } from "@/lib/api";
import { clearCache, useApi } from "@/lib/useApi";
import { useSession } from "@/lib/session";

/** Every business the caller created or belongs to — any role, any workspace. */
export default function Businesses() {
  const router = useRouter();
  const { switchTenant } = useSession();
  const { data, error, loading, reload } = useApi<any[]>("/my/businesses");
  const [creating, setCreating] = useState(false);

  const open = async (b: any) => {
    if (b.tenant_id !== currentTenant()) {
      await switchTenant(b.tenant_id);
      clearCache();
    }
    router.push(`/companies/${b.company_id}`);
  };

  if (loading) return <Loading rows={6} />;
  return (
    <>
      <PageHead title="My businesses" sub="Every business you created or belong to — owner, admin or member, across all workspaces."
        actions={<button className="btn pri" onClick={() => setCreating(true)}>New company</button>} />
      <ErrorBox error={error} retry={reload} />
      <ErrorBox error={error} retry={reload} />
      {!data?.length ? <p className="muted">No businesses yet. Companies you create or are invited to appear here.</p> : (
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
      {creating && <CompanyWizard onClose={() => { setCreating(false); reload(); }} onDone={(c) => open(c)} />}
    </>
  );
}
