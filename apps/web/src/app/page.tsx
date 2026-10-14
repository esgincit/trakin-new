"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Loading } from "@/components/ui";
import { isStaff, useSession } from "@/lib/session";

/** Sends each person to their own home page. */
export default function Home() {
  const { ready, session, workspace, me } = useSession();
  const router = useRouter();
  useEffect(() => {
    if (!ready) return;
    if (!session) return router.replace("/login");
    // No workspace yet (a new Google/Microsoft sign-up): the feed is their home.
    if (!workspace) return router.replace(me?.is_platform_admin ? "/platform" : "/network");
    if (workspace.role === "consultant") router.replace("/my");
    else if (!isStaff(workspace.role)) router.replace("/partner");
    else router.replace("/dashboard");
  }, [ready, session, workspace, me, router]);
  return <div className="content"><Loading /></div>;
}
