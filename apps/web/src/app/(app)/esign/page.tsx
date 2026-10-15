"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { DataTable } from "@/components/DataTable";
import { ErrorBox, PageHead } from "@/components/ui";
import { canEdit, useSession } from "@/lib/session";
import { useApi } from "@/lib/useApi";

export default function Envelopes() {
  const router = useRouter();
  const { workspace } = useSession();
  const { data, error, reload } = useApi<any[]>("/envelopes");
  return (
    <>
      <PageHead title="E-signatures" sub="MSAs, SOWs, amendments, NDAs and offers signed online. Every step records the time, IP address and device."
        actions={canEdit(workspace, "contracts") && <Link className="btn pri" href="/esign/new">Send a document</Link>} />
      <ErrorBox error={error} retry={reload} />
      <DataTable id="envelopes" rows={data} onRowClick={(r) => router.push(`/esign/${r.id}`)} columns={[
        { key: "number", label: "Envelope" }, { key: "title", label: "Document" },
        { key: "related", label: "For", value: (r) => r.agreement ?? r.sow ?? r.consultant ?? "–", hideSm: true },
        { key: "progress", label: "Signed", value: (r) => `${r.signed}/${r.signers}` },
        { key: "waiting_on", label: "Waiting on", hideSm: true },
        { key: "sent_at", label: "Sent", type: "date", hideSm: true }, { key: "completed_at", label: "Completed", type: "date" },
        { key: "status", label: "Status", type: "status", filter: true },
      ]} empty="Nothing sent yet." />
    </>
  );
}
