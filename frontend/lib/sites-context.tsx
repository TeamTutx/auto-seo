"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import type { Site } from "./types";

interface SitesContextValue {
  sites: Site[] | null;
  refreshSites: () => Promise<void>;
}

const SitesContext = createContext<SitesContextValue | undefined>(undefined);

// Sidebar and every dashboard page that lists/mutates sites share this one
// fetch instead of each keeping their own copy - otherwise deleting or
// renaming a site on one page leaves other already-mounted components
// (the sidebar, in particular) showing stale data until a full reload.
export function SitesProvider({ children }: { children: ReactNode }) {
  const [sites, setSites] = useState<Site[] | null>(null);

  const refreshSites = useCallback(async () => {
    try {
      setSites(await api.listSites());
    } catch {
      setSites([]);
    }
  }, []);

  useEffect(() => {
    refreshSites();
  }, [refreshSites]);

  return <SitesContext.Provider value={{ sites, refreshSites }}>{children}</SitesContext.Provider>;
}

export function useSites() {
  const ctx = useContext(SitesContext);
  if (!ctx) throw new Error("useSites must be used within SitesProvider");
  return ctx;
}
