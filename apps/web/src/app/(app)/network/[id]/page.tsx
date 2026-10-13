"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ProfileView } from "@/components/ProfileView";
import { Chip, ErrorBox, Loading, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export default function Person() {
  const { id } = useParams<{ id: string }>();
  const { data: p, error, loading, reload } = useApi(`/network/people/${id}`);
  const { run, busy } = useAction();
  if (loading) return <Loading rows={6} />;
  if (error) return <ErrorBox error={error} retry={reload} />;
  return <ProfileView p={p} actions={<>
    {!p.connection && <button className="btn pri" disabled={busy} onClick={async () => { if (await run(() => api(`/network/connections/${id}`, { method: "POST" }), "Invitation sent")) reload(); }}>Connect</button>}
    {p.connection?.status === "pending" && !p.connection.i_asked && <button className="btn pri" disabled={busy} onClick={async () => { if (await run(() => api(`/network/connections/${id}/respond`, { method: "POST", query: { accept: true } }), "Connected")) reload(); }}>Accept invitation</button>}
    {p.connection?.status === "pending" && p.connection.i_asked && <Chip status="pending">Invitation sent</Chip>}
    {p.connection?.status === "accepted" && <Chip status="accepted">Connected</Chip>}
    <Link className="btn" href={`/network?tab=messages&with=${id}`}>Message</Link>
  </>} />;
}
