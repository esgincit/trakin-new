import { api } from "./api";

/** Files above this go straight to storage: Vercel Functions accept request bodies up to 4.5 MB. */
export const DIRECT_LIMIT = 4 * 1024 * 1024;
export const MAX_UPLOAD = 25 * 1024 * 1024;

type Target = { purpose: "attachment"; owner_type: string; owner_id: string } | { purpose: "esign" };

/** Uploads a file to Supabase Storage through a one-time signed URL and returns its storage path. */
export async function uploadDirect(file: File, target: Target): Promise<string> {
  if (file.size > MAX_UPLOAD) throw new Error(`${file.name} is larger than 25 MB`);
  const start = await api<{ upload_url: string; path: string }>("/uploads", {
    body: { ...target, filename: file.name, content_type: file.type || "application/octet-stream", size: file.size },
  });
  const res = await fetch(start.upload_url, {
    method: "PUT",
    headers: { "Content-Type": file.type || "application/octet-stream", "x-upsert": "false" },
    body: file,
  });
  if (!res.ok) throw new Error(`Upload of ${file.name} failed (${res.status}). Please try again.`);
  return start.path;
}
