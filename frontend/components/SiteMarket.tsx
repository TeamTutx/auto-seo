"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useLocations } from "@/lib/use-locations";
import type { Site } from "@/lib/types";

/** Which country this site is measured in.
 *
 *  It drives the visibility check — Google, AI Overviews and ChatGPT — and is
 *  what the keyword form starts on. Before this existed every visibility reading
 *  in the product was taken from India, because the check used a default nobody
 *  passed and nothing recorded which country it meant.
 *
 *  Per site, not per account: one owner can run a UK shop and an Indian one, and
 *  a rank means nothing without knowing where it was measured. */
export default function SiteMarket({ site, onChanged }: { site: Site; onChanged: () => void }) {
  const { locations } = useLocations();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function change(code: number) {
    if (code === site.default_location_code) return;
    setBusy(true);
    setError(null);
    try {
      await api.updateSite(site.id, { default_location_code: code });
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not change the country.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel" style={{ padding: "14px 18px" }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>Measured in</span>
        <select
          className="admin-input"
          value={site.default_location_code}
          disabled={busy}
          onChange={(e) => change(Number(e.target.value))}
          style={{ fontSize: 12.5, padding: "6px 9px" }}
        >
          {locations.map((loc) => (
            <option key={loc.code} value={loc.code}>
              {loc.label}
            </option>
          ))}
        </select>
        <span style={{ fontSize: 12, color: "var(--text-muted)", flex: "1 1 260px", lineHeight: 1.45 }}>
          Where visibility checks search from, and what a new keyword defaults to. Keywords you already
          track keep the country they were added in.
        </span>
      </div>
      {error && <div className="form-error" style={{ fontSize: 12, marginTop: 8 }}>{error}</div>}
    </div>
  );
}
