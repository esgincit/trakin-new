"use client";

import { useEffect, useState } from "react";

/** Which social providers the Supabase project has switched on. `null` = couldn't find out. */
export type EnabledProviders = { google: boolean; azure: boolean } | null;

let cached: Promise<EnabledProviders> | null = null;

/** Reads Supabase's public auth settings once per page load. Never throws. */
function loadProviders(): Promise<EnabledProviders> {
  if (!cached) {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    cached = (async () => {
      if (!url || !key) return null;
      try {
        const res = await fetch(`${url.replace(/\/$/, "")}/auth/v1/settings`, { headers: { apikey: key } });
        if (!res.ok) return null;
        const external = (await res.json())?.external;
        if (!external) return null;
        return { google: !!external.google, azure: !!external.azure };
      } catch {
        return null;
      }
    })();
  }
  return cached;
}

/**
 * Providers that are enabled, so the sign-in page can hide a button that can't work yet
 * instead of showing a red error. Until the answer arrives (or if it can't be read) it
 * returns `null` and the page shows both buttons.
 */
export function useEnabledProviders(): EnabledProviders {
  const [providers, setProviders] = useState<EnabledProviders>(null);
  useEffect(() => {
    let alive = true;
    loadProviders().then((p) => alive && setProviders(p));
    return () => { alive = false; };
  }, []);
  return providers;
}
