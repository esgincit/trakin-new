"use client";

import { useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";

/** Acceptance history of an agreement or SOW (e-signed or recorded by staff), with "Record acceptance" (WF-06). */
export function Acceptance({ entityType, entityId, canRecord, onRecorded }: {
  entityType: "agreement" | "sow" | "amendment"; entityId: string; canRecord: boolean; onRecorded?: () => void;
}) {
  const history = useApi<any[]>("/acceptances", { entity_type: entityType, entity_id: entityId });
  const { run, busy } = useAction();
  return (
    <div className="card mt">
      <h3>Acceptance</h3>
      {history.data?.length ? history.data.map((a) => (
        <div key={a.id} className="alert">
          <div><b>{a.accepted_by}</b> · {a.method === "esign" ? "e-signed" : `recorded by ${a.recorded_by ?? "staff"}`}
            <div className="muted" style={{ fontSize: 12.5 }}>{dateTime(a.accepted_at)}{a.note && ` · ${a.note}`}</div></div>
        </div>
      )) : <p className="muted">Not accepted yet. Send it for e-signature, or record acceptance given on paper or by e-mail.</p>}
      {canRecord && (
        <button className="btn sm mt" disabled={busy} onClick={async () => {
          const by = prompt("Who accepted it? (name and company)");
          if (!by) return;
          const note = prompt("Note (optional) — e.g. 'Signed on paper, scanned copy attached'") ?? undefined;
          if (await run(() => api("/acceptances", { body: { entity_type: entityType, entity_id: entityId, accepted_by: by, note } }),
                        "Acceptance recorded")) { history.reload(); onRecorded?.(); }
        }}>Record acceptance</button>
      )}
    </div>
  );
}
