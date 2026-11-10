"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, createApiClient } from "./api";

export interface LoadState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

interface Settled<T> {
  key: string;
  data: T | null;
  error: string | null;
}

export function useLive<T>(load: (signal: { cancelled: boolean }) => Promise<T>, deps: unknown[] = []): LoadState<T> {
  const [tick, setTick] = useState(0);
  const [settled, setSettled] = useState<Settled<T>>({ key: "", data: null, error: null });
  const key = JSON.stringify(deps) + ":" + tick;

  useEffect(() => {
    const signal = { cancelled: false };
    load(signal)
      .then((value) => {
        if (!signal.cancelled) setSettled({ key, data: value, error: null });
      })
      .catch((reason: unknown) => {
        if (!signal.cancelled) setSettled({ key, data: null, error: reason instanceof ApiError ? reason.message : "加载失败" });
      });
    return () => {
      signal.cancelled = true;
    };
    // The key already captures deps and the reload tick.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const reload = useCallback(() => setTick((value) => value + 1), []);
  const current = settled.key === key;
  return { data: current ? settled.data : null, loading: !current, error: current ? settled.error : null, reload };
}

export function client() {
  return createApiClient();
}

export function messageOf(reason: unknown) {
  return reason instanceof ApiError ? reason.message : "操作失败";
}
