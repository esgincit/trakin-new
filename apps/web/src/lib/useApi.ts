"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";

// Small stale-while-revalidate cache: screens open instantly with the last data,
// then refresh in the background. Cleared on sign-out and workspace switch.
const cache = new Map<string, unknown>();
export const clearCache = () => cache.clear();

export function useApi<T = any>(path: string | null, query?: Record<string, any>) {
  const key = path ? path + JSON.stringify(query ?? {}) : null;
  const [data, setData] = useState<T | undefined>(key ? (cache.get(key) as T | undefined) : undefined);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(!!key && !cache.has(key));
  const latest = useRef(key);

  const load = useCallback(async () => {
    if (!path || !key) return;
    latest.current = key;
    setLoading(!cache.has(key));
    try {
      const result = await api<T>(path, { query });
      cache.set(key, result);
      if (latest.current === key) {
        setData(result);
        setError(null);
      }
    } catch (e) {
      if (latest.current === key) setError(e as ApiError);
    } finally {
      if (latest.current === key) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    if (key) setData(cache.get(key) as T | undefined);
    load();
  }, [key, load]);

  return { data, error, loading, reload: load, setData };
}
