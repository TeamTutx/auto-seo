"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import ScoreGauge from "@/components/ScoreGauge";
import CheckList from "@/components/CheckList";
import type { AuditDetail, Page, Site } from "@/lib/types";

export default function PageDetailPage() {
  const params = useParams<{ siteId: string; pageId: string }>();
  const siteId = Number(params.siteId);
  const pageId = Number(params.pageId);

  const [site, setSite] = useState<Site | null>(null);
  const [page, setPage] = useState<Page | null>(null);
  const [audit, setAudit] = useState<AuditDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

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
        <Link href={`/sites/${siteId}`}>{site.domain}</Link>
        {path !== "/" && <> / {path}</>}
      </div>
      <div className="detail-header">
        <div>
          <div className="detail-title">{audit?.extracted_title || path}</div>
          <div className="detail-url">{page.url}</div>
        </div>
        <button className="btn" onClick={handleRescan} disabled={running}>
          {running ? "Scanning…" : audit ? "Rescan page" : "Run first audit"}
        </button>
      </div>

      {error && <div className="form-error">{error}</div>}

      {!audit ? (
        <div className="panel empty-state">This page hasn&apos;t been audited yet.</div>
      ) : (
        <div className="detail-grid" style={{ display: "grid", gridTemplateColumns: "1fr 260px", gap: 20 }}>
          <div>
            <CheckList checks={audit.checks} />
          </div>
          <div>
            <div className="panel side-panel">
              <div className="gauge-label" style={{ textAlign: "center" }}>
                PAGE SCORE
              </div>
              <div style={{ display: "flex", justifyContent: "center", margin: "8px 0" }}>
                <ScoreGauge score={audit.score} />
              </div>
              <div className="kw-row" style={{ borderBottom: "1px solid var(--border)" }}>
                <span>Target keyword</span>
                <span>{page.target_keyword || "—"}</span>
              </div>
              <div className="kw-row" style={{ borderBottom: "1px solid var(--border)" }}>
                <span>Word count</span>
                <span>{audit.word_count ?? "—"}</span>
              </div>
              <div className="kw-row" style={{ borderBottom: "none" }}>
                <span>Last scanned</span>
                <span>{new Date(audit.created_at).toLocaleString()}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
