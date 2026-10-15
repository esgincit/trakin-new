"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { DataButtons } from "@/components/DataButtons";
import { DataTable, type Column } from "@/components/DataTable";
import { CompanyWizard } from "@/components/CompanyWizard";
import { Chip, ErrorBox, PageHead } from "@/components/ui";
import { allows, canEdit as permits, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

export default function Companies() {
  const router = useRouter();
  const { workspace } = useSession();
  const { data, error, reload } = useApi<any[]>("/companies");
  const [adding, setAdding] = useState(false);
  const money = allows(workspace, "finance");

  const columns: Column<any>[] = [
    { key: "business_code", label: "Business ID" },
    { key: "name", label: "Company" },
    { key: "kind", label: "Type", type: "label", filter: true },
    { key: "status", label: "Status", type: "status", filter: true },
    { key: "w9_status", label: "W-9", type: "label", hideSm: true },
    { key: "state", label: "State", filter: true, hideSm: true },
    { key: "contact_name", label: "Contact", hideSm: true },
    { key: "agreements", label: "Agreements", hideSm: true },
    { key: "next_expiry", label: "Next expiry", type: "date", hideSm: true },
    { key: "consultants", label: "Consultants", type: "number" },
    ...(money ? [{ key: "open_ar", label: "Open AR", type: "money" as const }, { key: "open_ap", label: "Open AP", type: "money" as const }] : []),
  ];

  return (
    <>
      <PageHead title="Clients & vendors" sub="Everyone you bill and everyone you pay — current and former. Inactive companies keep their full history."
        actions={allows(workspace, "account_manager", "finance", "legal") && permits(workspace, "companies") && <button className="btn pri" onClick={() => setAdding(true)}>New company</button>} />
      <ErrorBox error={error} retry={reload} />
      <DataTable id="companies" rows={data} columns={columns} onRowClick={(r) => router.push(`/companies/${r.id}`)}
                 cardAside={(r) => <Chip status={r.status} />} toolbar={<DataButtons entity="companies" label="companies" />} />
      {adding && <CompanyWizard onClose={() => { setAdding(false); reload(); }} onDone={(c) => router.push(`/companies/${c.id}`)} />}
    </>
  );
}
