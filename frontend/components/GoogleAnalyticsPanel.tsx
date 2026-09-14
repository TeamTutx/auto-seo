"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { GAPageMetrics } from "@/lib/types";

export default function GoogleAnalyticsPanel({ pageId }: { pageId: number }) {
  const [metrics, setMetrics] = useState<GAPageMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setMetrics(null);
    setError(null);

    api
      .getPageGAMetrics(pageId)
      .then((data) => !cancelled && setMetrics(data))
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load Analytics data.");
      });

    return () => {
      cancelled = true;
    };
  }, [pageId]);

  return (
    <div style={{ marginBottom: 32 }}>
      <div className="section-toolbar">
        <div className="section-title">Analytics — last 28 days</div>
      </div>

      {error && <div className="form-error">{error}</div>}

      {!error && !metrics && <div className="loading-state">Loading…</div>}

      {metrics && (
        <div className="stat-row stat-row-4">
          <div className="stat-cell">
            <div className="stat-label">Sessions</div>
            <div className="stat-value">{metrics.sessions}</div>
          </div>
          <div className="stat-cell">
            <div className="stat-label">Pageviews</div>
            <div className="stat-value">{metrics.pageviews}</div>
          </div>
          <div className="stat-cell">
            <div className="stat-label">Bounce rate</div>
            <div className="stat-value" style={{ fontSize: 20 }}>{metrics.bounce_rate}%</div>
          </div>
          <div className="stat-cell">
            <div className="stat-label">Avg. session</div>
            <div className="stat-value" style={{ fontSize: 20 }}>{Math.round(metrics.avg_session_duration)}s</div>
          </div>
        </div>
      )}
    </div>
  );
}
