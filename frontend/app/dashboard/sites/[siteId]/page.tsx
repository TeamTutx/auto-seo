"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useSiteJobs } from "@/lib/use-site-jobs";
import JobProgress from "@/components/JobProgress";
import { scoreBucket } from "@/lib/score";
import { useSites } from "@/lib/sites-context";
import SearchPresencePanel from "@/components/SearchPresencePanel";
import ScoreGauge from "@/components/ScoreGauge";
import SiteHealthPanel from "@/components/SiteHealthPanel";
import SiteVerification from "@/components/SiteVerification";
import type { Audit, IndexSummary, Page, Site } from "@/lib/types";

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
  const [indexSummary, setIndexSummary] = useState<IndexSummary | null>(null);
  const [crawling, setCrawling] = useState(false);

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

  const loadAll = useCallback(async () => {
    try {
      const [siteData, pages, summary] = await Promise.all([
        api.getSite(siteId),
        api.listPages(siteId),
        api.indexSummary(siteId).catch(() => null),
      ]);
      setSite(siteData);
      setIndexSummary(summary);
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
  }, [siteId]);

  // Refetch as soon as a crawl finishes rather than waiting for the next poll —
  // the pages it found are the whole point of having pressed the button.
  const onJobFinish = useCallback(
    (kind: string) => {
      if (kind === "crawl") loadAll();
    },
    [loadAll]
  );
  const { jobs } = useSiteJobs(siteId, onJobFinish);

  useEffect(() => {
    setRows(null);
    setNotFound(false);
    loadAll();
  }, [siteId, loadAll]);

  async function handleCrawl() {
    setCrawling(true);
    setBanner(null);
    try {
      await api.startCrawl(siteId);
    } catch (err) {
      setBanner(err instanceof ApiError ? err.message : "Could not start the crawl.");
    } finally {
      setCrawling(false);
    }
  }

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
      await api.updateSite(siteId, { domain: domainInput.trim() });
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
      router.push("/dashboard");
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

  const crawlJob = jobs?.crawl ?? null;
  const scored = rows.map((r) => r.latestAudit?.score).filter((s): s is number => typeof s === "number");
  const overallScore = scored.length > 0 ? Math.round(scored.reduce((a, b) => a + b, 0) / scored.length) : null;
  const unscanned = rows.filter((r) => !r.latestAudit).length;
  const needsAttention = rows.filter((r) => r.latestAudit && r.latestAudit.score !== null && r.latestAudit.score < 70).length;

  return (
    <div>
      <div className="topbar">
        <div style={{ flex: 1, minWidth: 240 }}>
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
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Link className="btn btn-ghost" href={`/dashboard/sites/${siteId}/opportunities`}>
            Fixes
          </Link>
          <Link className="btn btn-ghost" href={`/dashboard/sites/${siteId}/keywords`}>
            Keywords
          </Link>
          <Link className="btn btn-ghost" href={`/dashboard/sites/${siteId}/visibility`}>
            Visibility
          </Link>
          <button className="btn btn-ghost" onClick={handleCrawl} disabled={crawling || crawlJob?.status === "running"}>
            {crawlJob?.status === "running" ? "Finding pages…" : "Find pages"}
          </button>
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

      <JobProgress job={crawlJob} />

      <div style={{ marginBottom: 20 }}>
        <SiteVerification site={site} onVerified={loadAll} />
      </div>

      <div className="overview-grid">
        <div className="panel score-panel">
          <div className="gauge-label">OVERALL SEO SCORE</div>
          <ScoreGauge score={overallScore} />
        </div>

        <div className="stat-row stat-row-2x2">
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
          <div className="stat-cell">
            <div className="stat-label">Indexed by Google</div>
            <div className="stat-value">
              {indexSummary && indexSummary.total_pages > 0 && indexSummary.unchecked < indexSummary.total_pages
                ? indexSummary.indexed
                : "—"}
            </div>
            <div className="admin-hint">
              {!indexSummary || indexSummary.total_pages === 0
                ? "Find your pages first"
                : indexSummary.unchecked === indexSummary.total_pages
                ? "Connect Google to check"
                : indexSummary.not_indexed > 0
                ? `${indexSummary.not_indexed} not indexed`
                : "all indexed"}
            </div>
          </div>
        </div>
      </div>

      <SearchPresencePanel siteId={siteId} />

      <SiteHealthPanel siteId={siteId} />

      <div className="section-toolbar">
        <div className="section-title">Pages</div>
        <button className="btn-ghost btn" style={{ fontSize: 11.5, padding: "5px 10px" }} onClick={() => setAdding((v) => !v)}>
          {adding ? "Cancel" : "+ Add page"}
        </button>
      </div>

      {adding && (
        <form
          className="inline-form"
          onSubmit={handleAddPage}
          style={{ border: "1px solid var(--border)", borderRadius: 8, marginBottom: 10 }}
        >
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
        <div className="panel empty-state">No pages yet — add one to run your first audit.</div>
      ) : (
        <div className="card-grid" style={{ marginBottom: 0 }}>
          {rows.map(({ page, latestAudit }) => {
            const bucket = latestAudit ? scoreBucket(latestAudit.score) : null;
            const barColor =
              bucket === "good" ? "var(--good)" : bucket === "warn" ? "var(--warn)" : bucket === "bad" ? "var(--bad)" : "var(--border)";
            let path: string;
            try {
              path = new URL(page.url).pathname || "/";
            } catch {
              path = page.url;
            }
            return (
              <div className="page-card" key={page.id}>
                <div className="page-card-top" onClick={() => router.push(`/dashboard/sites/${siteId}/pages/${page.id}`)}>
                  <div style={{ minWidth: 0 }}>
                    <div className="page-path">{path}</div>
                    <div className="page-url">{page.url}</div>
                  </div>
                  {!latestAudit ? (
                    <span className="status-pill neutral">Not scanned</span>
                  ) : bucket === "good" ? (
                    <span className="status-pill good">Healthy</span>
                  ) : bucket === "warn" ? (
                    <span className="status-pill warn">Needs work</span>
                  ) : (
                    <span className="status-pill bad">Critical</span>
                  )}
                </div>
                <div className="mini-score">
                  <div className="mini-bar">
                    <div
                      className="mini-bar-fill"
                      style={{ width: latestAudit?.score != null ? `${latestAudit.score}%` : "0%", background: barColor }}
                    />
                  </div>
                  <span style={{ fontFamily: "var(--font-display)", fontSize: 12.5 }}>
                    {latestAudit?.score ?? "—"}
                  </span>
                </div>
                <div className="page-kw-row">
                  <span>Target keyword</span>
                  <span>{page.target_keyword || "—"}</span>
                </div>
                <div className="page-kw-row">
                  <span>Google index</span>
                  <span title={page.index_detail ?? undefined}>
                    {page.index_status === "indexed" ? (
                      <span className="index-pill indexed">Indexed</span>
                    ) : page.index_status === "not_indexed" ? (
                      <span className="index-pill missing">Not indexed</span>
                    ) : (
                      <span className="muted">not checked</span>
                    )}
                  </span>
                </div>
                <div className="page-card-actions">
                  <button
                    className="page-delete"
                    onClick={() => handleDeletePage(page.id, page.url)}
                    disabled={deletingPageId === page.id}
                  >
                    {deletingPageId === page.id ? "Deleting…" : "Delete"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

    </div>
  );
}
