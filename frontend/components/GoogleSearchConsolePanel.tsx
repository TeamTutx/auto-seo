"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { GSCIndexStatus, GSCQueryRow } from "@/lib/types";

export default function GoogleSearchConsolePanel({ pageId }: { pageId: number }) {
  const [indexStatus, setIndexStatus] = useState<GSCIndexStatus | null>(null);
  const [queries, setQueries] = useState<GSCQueryRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIndexStatus(null);
    setQueries(null);
    setError(null);

    Promise.all([api.getPageIndexStatus(pageId), api.getPageSearchQueries(pageId)])
      .then(([status, rows]) => {
        if (cancelled) return;
        setIndexStatus(status);
        setQueries(rows);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load Search Console data.");
      });

    return () => {
      cancelled = true;
    };
  }, [pageId]);

  return (
    <div style={{ marginBottom: 32 }}>
      <div className="section-toolbar">
        <div className="section-title">Search Console</div>
      </div>

      {error && (
        <div className="form-error" style={{ marginBottom: 10 }}>
          {error}
        </div>
      )}

      {!error && (indexStatus === null || queries === null) && <div className="loading-state">Loading…</div>}

      {indexStatus && (
        <div className="panel" style={{ padding: "14px 18px", marginBottom: 10, display: "flex", alignItems: "center", gap: 10 }}>
          <span className={`status-pill ${indexStatus.indexed ? "good" : "bad"}`}>
            {indexStatus.indexed ? "Indexed" : "Not indexed"}
          </span>
          <span style={{ fontSize: 12.5, color: "var(--text-muted)" }}>{indexStatus.coverage_state}</span>
        </div>
      )}

      {queries && (
        <div className="panel pages-panel">
          {queries.length === 0 ? (
            <div className="empty-state">No search queries recorded for this page in the last 28 days.</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Query</th>
                  <th>Clicks</th>
                  <th>Impressions</th>
                  <th>CTR</th>
                  <th>Avg. position</th>
                </tr>
              </thead>
              <tbody>
                {queries.map((row) => (
                  <tr key={row.query}>
                    <td>{row.query}</td>
                    <td>{row.clicks}</td>
                    <td>{row.impressions}</td>
                    <td>{row.ctr}%</td>
                    <td>{row.position}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
