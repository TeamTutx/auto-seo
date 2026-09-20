"use client";

import { Suspense, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { routes, useRouteId } from "@/lib/routes";
import ScoreGauge from "@/components/ScoreGauge";
import CheckList from "@/components/CheckList";
import GoogleAnalyticsPanel from "@/components/GoogleAnalyticsPanel";
import GoogleSearchConsolePanel from "@/components/GoogleSearchConsolePanel";
import KeywordPanel from "@/components/KeywordPanel";
import type { AuditDetail, Page, Site } from "@/lib/types";

function PageDetailPage() {
  const siteId = useRouteId("site");
  const pageId = useRouteId("id");
  const router = useRouter();

  const [site, setSite] = useState<Site | null>(null);
  const [page, setPage] = useState<Page | null>(null);
  const [audit, setAudit] = useState<AuditDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [editing, setEditing] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [keywordInput, setKeywordInput] = useState("");
  const [editError, setEditError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function load() {
    try {
      const [siteData, pageData, audits] = await Promise.all([
        api.getSite(siteId),
        api.getPage(pageId),
        api.listAudits(pageId),
      ]);
      setSite(siteData);
      setPage(pageData);
      if (audits.length > 0) {
        setAudit(await api.getAudit(audits[0].id));
      } else {
        setAudit(null);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setNotFound(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageId]);

  async function handleRescan() {
    setRunning(true);
    setError(null);
    try {
      const result = await api.runAudit(pageId);
      setAudit(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not run audit.");
    } finally {
      setRunning(false);
    }
  }

  async function handleSaveEdit(e: FormEvent) {
    e.preventDefault();
    setEditError(null);
    setSaving(true);
    try {
      const updated = await api.updatePage(pageId, { url: urlInput.trim(), target_keyword: keywordInput.trim() });
      setPage(updated);
      setEditing(false);
    } catch (err) {
      setEditError(err instanceof ApiError ? err.message : "Could not update page.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeletePage() {
    if (!page || !confirm(`Delete ${page.url}? This removes its audit history and tracked keywords.`)) return;
    setDeleting(true);
    try {
      await api.deletePage(pageId);
      router.push(routes.site(siteId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete page.");
      setDeleting(false);
    }
  }

  if (notFound) return <div className="empty-state">Page not found.</div>;
  if (loading || !site || !page) return <div className="loading-state">Loading…</div>;

  let path: string;
  try {
    path = new URL(page.url).pathname || "/";
  } catch {
    path = page.url;
  }

  return (
    <div>
      <div className="breadcrumb">
        <Link href={routes.site(siteId)}>{site.domain}</Link>
        {path !== "/" && <> / {path}</>}
      </div>
      <div className="detail-header">
        {editing ? (
          <form onSubmit={handleSaveEdit} style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>
            <input
              autoFocus
              type="url"
              required
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              style={{
                background: "var(--bg)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "8px 10px",
                color: "var(--text)",
                fontSize: 13.5,
              }}
            />
            <input
              type="text"
              placeholder="Target keyword (optional)"
              value={keywordInput}
              onChange={(e) => setKeywordInput(e.target.value)}
              style={{
                background: "var(--bg)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "8px 10px",
                color: "var(--text)",
                fontSize: 13.5,
              }}
            />
            {editError && <div style={{ color: "var(--bad)", fontSize: 12.5 }}>{editError}</div>}
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn" type="submit" disabled={saving}>
                Save
              </button>
              <button type="button" className="btn-ghost btn" onClick={() => setEditing(false)}>
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <>
            <div>
              <div className="detail-title">{audit?.extracted_title || path}</div>
              <div className="detail-url">{page.url}</div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn" onClick={handleRescan} disabled={running}>
                {running ? "Scanning…" : audit ? "Rescan page" : "Run first audit"}
              </button>
              <button
                className="btn-ghost btn"
                onClick={() => {
                  setUrlInput(page.url);
                  setKeywordInput(page.target_keyword || "");
                  setEditing(true);
                }}
              >
                Edit
              </button>
              <button className="btn-ghost btn" onClick={handleDeletePage} disabled={deleting} style={{ color: "var(--bad)" }}>
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </div>
          </>
        )}
      </div>

      {error && <div className="form-error">{error}</div>}

      {audit && (
        <div className="overview-grid">
          <div className="panel score-panel">
            <div className="gauge-label">PAGE SCORE</div>
            <ScoreGauge score={audit.score} />
          </div>
          <div className="stat-row">
            <div className="stat-cell">
              <div className="stat-label">Target keyword</div>
              <div className="stat-value" style={{ fontSize: 16.5 }}>{page.target_keyword || "—"}</div>
            </div>
            <div className="stat-cell">
              <div className="stat-label">Word count</div>
              <div className="stat-value">{audit.word_count ?? "—"}</div>
            </div>
            <div className="stat-cell">
              <div className="stat-label">Last scanned</div>
              <div className="stat-value" style={{ fontSize: 14.5 }}>{new Date(audit.created_at).toLocaleString()}</div>
            </div>
          </div>
        </div>
      )}

      {!audit ? (
        <div className="panel empty-state" style={{ marginBottom: 32 }}>This page hasn&apos;t been audited yet.</div>
      ) : (
        <CheckList checks={audit.checks} pageId={pageId} />
      )}

      <KeywordPanel pageId={pageId} />

      {site.gsc_property && <GoogleSearchConsolePanel pageId={pageId} />}
      {site.ga_property_id && <GoogleAnalyticsPanel pageId={pageId} />}
    </div>
  );
}

// useSearchParams has to sit inside a Suspense boundary or `next build` fails
// (see CLAUDE.md). Same shape as /login, which has always read its query string.
export default function Page() {
  return (
    <Suspense fallback={<div className="loading-state">Loading…</div>}>
      <PageDetailPage />
    </Suspense>
  );
}
