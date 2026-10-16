"use client";

import Link from "next/link";
import { download } from "@/lib/api";
import { allows, useSession } from "@/lib/session";
import { iso } from "@/lib/weeks";

/** Template / import / export shortcuts shown above lists that support bulk data. */
export function DataButtons({ entity, label }: { entity: string; label: string }) {
  const { workspace } = useSession();
  if (!allows(workspace, "finance", "hr", "legal", "account_manager")) return null;
  const day = iso(new Date());
  return (
    <>
      <button className="btn sm" onClick={() => download(`/data/templates/${entity}.csv`, `mytrakin-${entity}-template.csv`)} title={`Blank ${label} template with sample rows`}>Template</button>
      <Link className="btn sm" href={`/data?entity=${entity}`}>Import</Link>
      <button className="btn sm" onClick={() => download(`/data/export/${entity}.csv`, `mytrakin-${entity}-${day}.csv`)} title="Full export in the template's columns">Export all</button>
    </>
  );
}
