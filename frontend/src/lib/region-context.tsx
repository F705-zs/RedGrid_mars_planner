import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { useRegions } from "@/api/queries";
import type { Region } from "@/types";

// Selected region is a small UI preference, so it may live in localStorage.
const PREF_KEY = "redgrid.regionId";

interface RegionContextValue {
  regions: Region[] | undefined;
  region: Region | undefined;
  setRegionId: (id: number) => void;
  isLoading: boolean;
  error: unknown;
  refetch: () => Promise<unknown>;
}

const RegionContext = createContext<RegionContextValue | null>(null);

export function RegionProvider({ children }: { children: ReactNode }) {
  const { data: regions, isLoading, error, refetch } = useRegions();
  const [regionId, setRegionIdState] = useState<number | null>(null);

  useEffect(() => {
    const stored = Number(window.localStorage.getItem(PREF_KEY));
    if (Number.isInteger(stored) && stored > 0) setRegionIdState(stored);
  }, []);

  const value = useMemo<RegionContextValue>(() => {
    const region = regions?.find((r) => r.id === regionId) ?? regions?.[0];
    return {
      regions,
      region,
      isLoading,
      error,
      refetch,
      setRegionId: (id) => {
        setRegionIdState(id);
        window.localStorage.setItem(PREF_KEY, String(id));
      },
    };
  }, [regions, regionId, isLoading, error, refetch]);

  return <RegionContext.Provider value={value}>{children}</RegionContext.Provider>;
}

export function useRegionContext() {
  const ctx = useContext(RegionContext);
  if (!ctx) throw new Error("useRegionContext must be used inside RegionProvider");
  return ctx;
}

/** Looks up a region by id from the loaded list (e.g. a mission's region). */
export function useRegionById(id: number | undefined) {
  const { regions } = useRegionContext();
  return regions?.find((r) => r.id === id);
}
