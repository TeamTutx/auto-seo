"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { scoreBucket } from "@/lib/score";
import { useSites } from "@/lib/sites-context";
import ScoreGauge from "@/components/ScoreGauge";
import type { Audit, Page, Site } from "@/lib/types";

interface PageRow {
  page: Page;
  latestAudit: Audit | null;
}

export default function SiteOverviewPage() {
  const params = useParams<{ siteId: string }>();
  const siteId = Number(params.siteId);
  const router = useRouter();
  const { refreshSites } = useSites();

  const [site, setSite] = useState<Site | null>(null);
  const [rows, setRows] = useState<PageRow[] | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  const [adding, setAdding] = useState(false);
  const [url, setUrl] = useState("");
  const [keyword, setKeyword] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [editingDomain, setEditingDomain] = useState(false);
  const [domainInput, setDomainInput] = useState("");
  const [domainError, setDomainError] = useState<string | null>(null);
  const [savingDomain, setSavingDomain] = useState(false);
  const [deletingSite, setDeletingSite] = useState(false);
  const [deletingPageId, setDeletingPageId] = useState<number | null>(null);

  async function loadAll() {
    try {
      const [siteData, pages] = await Promise.all([api.getSite(siteId), api.listPages(siteId)]);
      setSite(siteData);
      const withAudits = await Promise.all(
        pages.map(async (page) => {
          const audits = await api.listAudits(page.id);
          return { page, latestAudit: audits[0] ?? null };
        })
      );
      setRows(withAudits);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setNotFound(true);
    }
  }

  useEffect(() => {
    setRows(null);
    setNotFound(false);
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId]);

  async function handleAddPage(e: FormEvent) {
    e.preventDefault();
    setAddError(null);
    setSubmitting(true);
    try {
      await api.createPage(siteId, url.trim(), keyword.trim() || undefined);
      setUrl("");
      setKeyword("");
      setAdding(false);
      await loadAll();
    } catch (err) {
      setAddError(err instanceof ApiError ? err.message : "Could not add page.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSaveDomain(e: FormEvent) {
    e.preventDefault();
    setDomainError(null);
    setSavingDomain(true);
    try {
      await api.updateSite(siteId, domainInput.trim());
      setEditingDomain(false);
      await Promise.all([loadAll(), refreshSites()]);
    } catch (err) {
      setDomainError(err instanceof ApiError ? err.message : "Could not update domain.");
    } finally {
      setSavingDomain(false);
    }
  }

  async function handleDeleteSite() {
    if (!confirm(`Delete ${site?.domain}? This removes every page, audit, and tracked keyword under it.`)) return;
    setDeletingSite(true);
    try {
      await api.deleteSite(siteId);
      await refreshSites();
      router.push("/");
    } catch (err) {
      setBanner(err instanceof ApiError ? err.message : "Could not delete site.");
      setDeletingSite(false);
    }
  }

  async function handleDeletePage(pageId: number, pageUrl: string) {
    if (!confirm(`Delete ${pageUrl}? This removes its audit history and tracked keywords.`)) return;
    setDeletingPageId(pageId);
    try {
      await api.deletePage(pageId);
      await loadAll();
    } catch (err) {
      setBanner(err instanceof ApiError ? err.message : "Could not delete page.");
    } finally {
      setDeletingPageId(null);
    }
  }

  async function handleRunFullScan() {
    if (!rows || rows.length === 0) return;
    setScanning(true);
    setBanner(null);
    let failures = 0;
    for (const row of rows) {
      try {
        await api.runAudit(row.page.id);
      } catch {
        failures += 1;
      }
    }
    setScanning(false);
    if (failures > 0) {
      setBanner(`${failures} page(s) could not be rescanned (rate limit or fetch error).`);
    }
    await loadAll();
  }

  if (notFound) {
    return <div className="empty-state">Site not found.</div>;
  }

  if (!site || rows === null) {
    return <div className="loading-state">Loading…</div>;
  }

  const scored = rows.map((r) => r.latestAudit?.score).filter((s): s is number => typeof s === "number");
  const overallScore = scored.length > 0 ? Math.round(scored.reduce((a, b) => a + b, 0) / scored.length) : null;
  const unscanned = rows.filter((r) => !r.latestAudit).length;
  const needsAttention = rows.filter((r) => r.latestAudit && r.latestAudit.score !== null && r.latestAudit.score < 70).length;

  return (
    <div>
      <div className="topbar">
        <div style={{ flex: 1, minWidth: 0 }}>
          {editingDomain ? (
            <form onSubmit={handleSaveDomain} style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                autoFocus
                value={domainInput}
                onChange={(e) => setDomainInput(e.target.value)}
                style={{
                  background: "var(--bg)",
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                  padding: "6px 10px",
                  color: "var(--text)",
                  fontSize: 18,
                  fontFamily: "var(--font-display)",
                  minWidth: 220,
                }}
              />
              <button className="btn" type="submit" disabled={savingDomain || !domainInput.trim()} style={{ fontSize: 12.5 }}>
                Save
              </button>
              <button
                type="button"
                className="btn-ghost btn"
                style={{ fontSize: 12.5 }}
                onClick={() => {
                  setEditingDomain(false);
                  setDomainError(null);
                }}
              >
                Cancel
              </button>
            </form>
          ) : (
            <div className="page-title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {site.domain}
              <button
                className="btn-ghost btn"
                style={{ fontSize: 11, padding: "4px 9px" }}
                onClick={() => {
                  setDomainInput(site.domain);
                  setEditingDomain(true);
                }}
              >
                Edit
              </button>
            </div>
          )}
          {domainError && <div style={{ color: "var(--bad)", fontSize: 12, marginTop: 4 }}>{domainError}</div>}
          <div className="page-sub">
            {rows.length} page{rows.length === 1 ? "" : "s"} tracked
            {!site.verified && " · domain not verified"}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn" onClick={handleRunFullScan} disabled={scanning || rows.length === 0}>
            {scanning ? "Scanning…" : "Run full scan"}
          </button>
          <button className="btn-ghost btn" onClick={handleDeleteSite} disabled={deletingSite} style={{ color: "var(--bad)" }}>
            {deletingSite ? "Deleting…" : "Delete site"}
          </button>
        </div>
      </div>

      {banner && (
        <div className="form-error" style={{ marginBottom: 20 }}>
          {banner}
        </div>
      )}

      <div className="overview-grid">
        <div className="panel score-panel">
          <div className="gauge-label">OVERALL SEO SCORE</div>
          <ScoreGauge score={overallScore} />
        </div>

        <div className="stat-row">
          <div className="stat-cell">
            <div className="stat-label">Pages tracked</div>
            <div className="stat-value">{rows.length}</div>
          </div>
          <div className="stat-cell">
            <div className="stat-label">Not yet scanned</div>
            <div className="stat-value">{unscanned}</div>
          </div>
          <div className="stat-cell">
            <div className="stat-label">Needs attention</div>
            <div className="stat-value">{needsAttention}</div>
          </div>
        </div>
      </div>

      <div className="panel pages-panel">
        <div className="pages-header">
          <h3>Pages</h3>
          <button className="btn btn-ghost" onClick={() => setAdding((v) => !v)}>
            {adding ? "Cancel" : "+ Add page"}
          </button>
        </div>

        {adding && (
          <form className="inline-form" onSubmit={handleAddPage}>
            <input
              type="url"
              required
              placeholder="https://example.com/page"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <input
              type="text"
              placeholder="Target keyword (optional)"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
            <button className="btn" type="submit" disabled={submitting}>
              Add
            </button>
            {addError && <div style={{ color: "var(--bad)", fontSize: 12.5, flexBasis: "100%" }}>{addError}</div>}
          </form>
        )}

        {rows.length === 0 ? (
          <div className="empty-state">No pages yet — add one to run your first audit.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Page</th>
                <th>Score</th>
                <th>Target keyword</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ page, latestAudit }) => {
                const bucket = latestAudit ? scoreBucket(latestAudit.score) : null;
                let path: string;
                try {
                  path = new URL(page.url).pathname || "/";
                } catch {
                  path = page.url;
                }
                return (
                  <tr
                    key={page.id}
                    className="clickable"
                    onClick={() => router.push(`/sites/${siteId}/pages/${page.id}`)}
                  >
                    <td>
                      <div className="url-cell">
                        <span className="url-path">{path}</span>
                        <span className="url-full">{page.url}</span>
                      </div>
                    </td>
                    <td>
                      {latestAudit && latestAudit.score !== null ? (
                        <div className="mini-score">
                          <div className="mini-bar">
                            <div
                              className="mini-bar-fill"
                              style={{
                                width: `${latestAudit.score}%`,
                                background:
                                  bucket === "good" ? "var(--good)" : bucket === "warn" ? "var(--warn)" : "var(--bad)",
                              }}
                            />
                          </div>
                          {latestAudit.score}
                        </div>
                      ) : (
                        <span style={{ color: "var(--text-muted)" }}>—</span>
                      )}
                    </td>
                    <td>{page.target_keyword || <span style={{ color: "var(--text-muted)" }}>—</span>}</td>
                    <td>
                      {!latestAudit ? (
                        <span className="status-pill neutral">Not scanned</span>
                      ) : bucket === "good" ? (
                        <span className="status-pill good">Healthy</span>
                      ) : bucket === "warn" ? (
                        <span className="status-pill warn">Needs work</span>
                      ) : (
                        <span className="status-pill bad">Critical</span>
                      )}
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <button
                        className="btn-ghost btn"
                        style={{ fontSize: 11, padding: "4px 9px", color: "var(--bad)" }}
                        onClick={() => handleDeletePage(page.id, page.url)}
                        disabled={deletingPageId === page.id}
                      >
                        {deletingPageId === page.id ? "Deleting…" : "Delete"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
