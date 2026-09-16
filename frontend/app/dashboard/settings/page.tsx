"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useSites } from "@/lib/sites-context";
import type { GoogleConnectionStatus } from "@/lib/types";

export default function SettingsPage() {
  return (
    <Suspense fallback={<div className="loading-state">Loading…</div>}>
      <SettingsContent />
    </Suspense>
  );
}

function SettingsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { sites, refreshSites } = useSites();

  const [status, setStatus] = useState<GoogleConnectionStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [bannerIsError, setBannerIsError] = useState(false);
  const [savingSiteId, setSavingSiteId] = useState<number | null>(null);

  async function loadStatus() {
    try {
      setStatus(await api.getGoogleStatus());
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Could not load Google connection status.");
    }
  }

  useEffect(() => {
    loadStatus();

    const connected = searchParams.get("google");
    const error = searchParams.get("google_error");
    if (connected === "connected") {
      setBanner("Google account connected.");
      setBannerIsError(false);
    } else if (error) {
      setBanner(error);
      setBannerIsError(true);
    }
    if (connected || error) {
      router.replace("/dashboard/settings");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleConnect() {
    setConnecting(true);
    setLoadError(null);
    try {
      const { authorize_url } = await api.connectGoogle();
      window.location.href = authorize_url;
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Could not start the Google connection.");
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    if (!confirm("Disconnect your Google account? Search Console and Analytics data will stop showing on your pages.")) return;
    setDisconnecting(true);
    try {
      await api.disconnectGoogle();
      await loadStatus();
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Could not disconnect.");
    } finally {
      setDisconnecting(false);
    }
  }

  async function handlePropertyChange(siteId: number, field: "gsc_property" | "ga_property_id", value: string) {
    setSavingSiteId(siteId);
    try {
      await api.updateSite(siteId, { [field]: value || null });
      await refreshSites();
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Could not save that property.");
    } finally {
      setSavingSiteId(null);
    }
  }

  return (
    <div>
      <div className="topbar">
        <div>
          <div className="page-title">Settings</div>
          <div className="page-sub">Connect Google Search Console and Analytics for real search and traffic data.</div>
        </div>
      </div>

      {banner && (
        <div className={bannerIsError ? "form-error" : "note"} style={{ marginBottom: 20 }}>
          {banner}
        </div>
      )}
      {loadError && (
        <div className="form-error" style={{ marginBottom: 20 }}>
          {loadError}
        </div>
      )}

      <div className="panel" style={{ padding: 22, marginBottom: 24 }}>
        <h3 style={{ marginBottom: 4 }}>Google account</h3>
        {status === null ? (
          <div className="loading-state">Loading…</div>
        ) : status.connected ? (
          <>
            <div style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 14 }}>
              Connected{status.connected_at ? ` on ${new Date(status.connected_at).toLocaleDateString()}` : ""}.
              {status.gsc_properties.length === 0 && status.ga_properties.length === 0 && (
                <> No Search Console or Analytics properties were found on this account.</>
              )}
            </div>
            <button className="btn-ghost btn" onClick={handleDisconnect} disabled={disconnecting} style={{ color: "var(--bad)" }}>
              {disconnecting ? "Disconnecting…" : "Disconnect"}
            </button>
          </>
        ) : (
          <>
            <div style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 14 }}>
              Not connected. Connecting lets Signal show real search queries, impressions, indexing status, and
              traffic per page instead of just what it can measure on its own.
            </div>
            <button className="btn" onClick={handleConnect} disabled={connecting}>
              {connecting ? "Redirecting…" : "Connect Google"}
            </button>
          </>
        )}
      </div>

      {status?.connected && sites && sites.length > 0 && (
        <div className="panel pages-panel">
          <div className="pages-header">
            <h3>Site properties</h3>
          </div>
          <table>
            <thead>
              <tr>
                <th>Site</th>
                <th>Search Console property</th>
                <th>Analytics property</th>
              </tr>
            </thead>
            <tbody>
              {sites.map((site) => (
                <tr key={site.id}>
                  <td>{site.domain}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <select
                      value={site.gsc_property ?? ""}
                      disabled={savingSiteId === site.id}
                      onChange={(e) => handlePropertyChange(site.id, "gsc_property", e.target.value)}
                      style={{
                        background: "var(--bg)",
                        border: "1px solid var(--border)",
                        borderRadius: 6,
                        padding: "6px 8px",
                        color: "var(--text)",
                        fontSize: 12.5,
                        width: "100%",
                      }}
                    >
                      <option value="">Not linked</option>
                      {status.gsc_properties.map((prop) => (
                        <option key={prop} value={prop}>
                          {prop}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <select
                      value={site.ga_property_id ?? ""}
                      disabled={savingSiteId === site.id}
                      onChange={(e) => handlePropertyChange(site.id, "ga_property_id", e.target.value)}
                      style={{
                        background: "var(--bg)",
                        border: "1px solid var(--border)",
                        borderRadius: 6,
                        padding: "6px 8px",
                        color: "var(--text)",
                        fontSize: 12.5,
                        width: "100%",
                      }}
                    >
                      <option value="">Not linked</option>
                      {status.ga_properties.map((prop) => (
                        <option key={prop.property_id} value={prop.property_id}>
                          {prop.display_name || prop.property_id}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
