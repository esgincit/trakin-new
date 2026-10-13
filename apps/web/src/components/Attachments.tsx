"use client";

import { useRef } from "react";
import { api } from "@/lib/api";
import { DIRECT_LIMIT, uploadDirect } from "@/lib/upload";
import { date } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useAction } from "./ui";

/** Extra files on any record: upload, open (short-lived link), remove. */
export function Attachments({ ownerType, ownerId, canEdit = true }: { ownerType: string; ownerId: string; canEdit?: boolean }) {
  const { data, reload } = useApi<any[]>("/files", { owner_type: ownerType, owner_id: ownerId });
  const input = useRef<HTMLInputElement>(null);
  const { run, busy } = useAction();

  const upload = async (files: FileList | null) => {
    for (const file of Array.from(files ?? [])) {
      if (file.size > DIRECT_LIMIT) {
        // Large files go straight to storage, then get recorded.
        await run(async () => {
          const path = await uploadDirect(file, { purpose: "attachment", owner_type: ownerType, owner_id: ownerId });
          return api("/files/confirm", { body: { owner_type: ownerType, owner_id: ownerId, path, name: file.name, content_type: file.type } });
        }, `${file.name} uploaded`);
        continue;
      }
      const form = new FormData();
      form.set("owner_type", ownerType);
      form.set("owner_id", ownerId);
      form.set("file", file);
      await run(() => api("/files", { form }), `${file.name} uploaded`);
    }
    if (input.current) input.current.value = "";
    reload();
  };

  const open = async (id: string) => {
    const r = await run(() => api(`/files/${id}/link`));
    if (r) window.open(r.url, "_blank", "noopener");
  };

  return (
    <div className="card mt">
      <div className="row">
        <h3 style={{ flex: 1, margin: 0 }}>Files</h3>
        {canEdit && (
          <>
            <input ref={input} type="file" multiple hidden onChange={(e) => upload(e.target.files)} />
            <button className="btn sm" disabled={busy} onClick={() => input.current?.click()}>Add files</button>
          </>
        )}
      </div>
      {data?.length ? (
        <div className="ftiles mt">
          {data.map((f) => (
            <div key={f.id} className="ftile">
              <div className="fext">{(f.name.split(".").pop() ?? "file").toUpperCase().slice(0, 4)}</div>
              <div className="fname" title={f.name}>{f.name}</div>
              <div className="muted" style={{ fontSize: 11.5 }}>{date(f.created_at)} · {Math.ceil(f.size_bytes / 1024)} KB</div>
              <div className="row" style={{ justifyContent: "center", marginTop: 6 }}>
                <button className="btn sm" onClick={() => open(f.id)}>Open</button>
                {canEdit && <button className="btn sm" onClick={async () => { if (confirm(`Remove ${f.name}?`)) { await run(() => api(`/files/${f.id}`, { method: "DELETE" }), "Removed"); reload(); } }}>Remove</button>}
              </div>
            </div>
          ))}
        </div>
      ) : <p className="muted" style={{ marginBottom: 0 }}>No files yet. Add PDFs, images, spreadsheets — up to 25 MB each.</p>}
    </div>
  );
}
