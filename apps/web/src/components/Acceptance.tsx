"use client";

import { useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";

/** Acceptance history of an agreement or SOW (e-signed or recorded by staff), with "Record acceptance" (WF-06). */
export function Acceptance({ entityType, entityId, canRecord, onRecorded, active }: {
  entityType: "agreement" | "sow" | "amendment"; entityId: string; canRecord: boolean; onRecorded?: () => void;
  active?: boolean;   // already active without an acceptance record = recorded as signed elsewhere
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
      )) : active
        ? <p className="muted">Recorded as already signed outside myTrakIn — no acceptance details were captured.</p>
        : <p className="muted">Not accepted yet. Send it for e-signature, or record acceptance given on paper or by e-mail.</p>}
      {canRecord && (
        <button className="btn sm mt" disabled={busy} onClick={async () => {
          const by = prompt("Who accepted it? (name and company)");
          if (by === null) return;
          if (by.trim().length < 2) return alert("Enter the name of the person who accepted it (at least 2 characters).");
          const note = prompt("Note (optional) — e.g. 'Signed on paper, scanned copy attached'") ?? undefined;
          if (await run(() => api("/acceptances", { body: { entity_type: entityType, entity_id: entityId, accepted_by: by, note } }),
                        "Acceptance recorded")) { history.reload(); onRecorded?.(); }
        }}>Record acceptance</button>
      )}
    </div>
  );
}
