"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { FALLBACK_LOCATION, type LocationOption, type SearchLocation } from "@/lib/types";

/** The countries a search can be measured in.
 *
 *  Fetched rather than hardcoded so the owner can add a market from /admin
 *  without a deploy. Falls back to a single entry if the request fails: a
 *  country dropdown with nothing in it cannot be used at all, and an empty list
 *  would make the keyword form look broken rather than degraded. */
export function useLocations(): { locations: LocationOption[]; loaded: boolean } {
  const [locations, setLocations] = useState<LocationOption[]>([FALLBACK_LOCATION]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .listLocations()
      .then((rows: SearchLocation[]) => {
        if (cancelled || rows.length === 0) return;
        setLocations(rows.map((r) => ({ code: r.code, label: r.label })));
      })
      .catch(() => undefined)
      .finally(() => !cancelled && setLoaded(true));
    return () => {
      cancelled = true;
    };
  }, []);

  return { locations, loaded };
}

/** A country's name for display, falling back to the raw provider code so a
 *  reading from a since-retired market still says where it was taken. */
export function locationLabel(locations: LocationOption[], code: number): string {
  return locations.find((l) => l.code === code)?.label ?? `Location ${code}`;
}
