"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useSites } from "@/lib/sites-context";
import AlertsBell from "./AlertsBell";

const PLAN_LABEL: Record<string, string> = {
  free: "Free plan",
  pro: "Pro plan",
  agency: "Agency plan",
};

export default function Sidebar() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const params = useParams<{ siteId?: string }>();
  const activeSiteId = params?.siteId ? Number(params.siteId) : null;

  const { sites, refreshSites } = useSites();
  const [adding, setAdding] = useState(false);
  const [domain, setDomain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleAddSite(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const site = await api.createSite(domain.trim());
      setDomain("");
      setAdding(false);
      await refreshSites();
      router.push(`/sites/${site.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add site.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark" />
        <div className="brand-name">Signal</div>
      </div>

      <div className="nav-section" style={{ flex: 1, overflow: "auto" }}>
        <div className="nav-label">SITES</div>
        <div className="site-list">
          {sites === null && <div className="footer-text">Loading…</div>}
          {sites?.length === 0 && <div className="footer-text">No sites yet</div>}
          {sites?.map((site) => (
            <Link
              key={site.id}
              href={`/sites/${site.id}`}
              className={`site-item ${activeSiteId === site.id ? "active" : ""}`}
            >
              <div className="site-item-name">
                <span className={`dot ${site.verified ? "good" : "neutral"}`} />
                {site.domain}
              </div>
            </Link>
          ))}
        </div>

        {adding ? (
          <form onSubmit={handleAddSite} style={{ marginTop: 8, padding: "0 8px" }}>
            <input
              autoFocus
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="example.com"
              style={{
                width: "100%",
                background: "var(--bg)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "7px 9px",
                color: "var(--text)",
                fontSize: 13,
                marginBottom: 6,
              }}
            />
            {error && <div style={{ color: "var(--bad)", fontSize: 11.5, marginBottom: 6 }}>{error}</div>}
            <div style={{ display: "flex", gap: 6 }}>
              <button className="btn" type="submit" disabled={submitting || !domain.trim()} style={{ flex: 1, fontSize: 12 }}>
                Add
              </button>
              <button
                type="button"
                className="btn-ghost btn"
                style={{ flex: 1, fontSize: 12 }}
                onClick={() => {
                  setAdding(false);
                  setError(null);
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <button className="add-site-btn" onClick={() => setAdding(true)}>
            + Add site
          </button>
        )}
      </div>

      <Link
        href="/settings"
        className="add-site-btn"
        style={{ textDecoration: "none", justifyContent: "flex-start" }}
      >
        Settings
      </Link>

      {user && (
        <div className="plan-widget">
          <div className="plan-widget-top">
            <div className="plan-name">{PLAN_LABEL[user.plan] ?? user.plan}</div>
            <AlertsBell />
          </div>
          <div className="plan-credits">{user.credits_balance} credits remaining</div>
        </div>
      )}

      <div className="sidebar-footer">
        <div className="footer-user">
          <div className="avatar">{user?.email.slice(0, 2).toUpperCase() ?? "?"}</div>
          <div className="footer-text">{user?.email}</div>
        </div>
        <button
          className="logout-btn"
          onClick={() => {
            logout();
            router.push("/login");
          }}
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
