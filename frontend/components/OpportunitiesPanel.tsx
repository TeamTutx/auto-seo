"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Opportunity, OpportunitySeverity } from "@/lib/types";

const SEVERITY_PILL: Record<OpportunitySeverity, string> = {
  high: "bad",
  medium: "warn",
  low: "neutral",
};

const TYPE_LABEL: Record<Opportunity["type"], string> = {
  audit_fail: "Audit",
  audit_warning: "Audit",
  keyword_not_found: "Keyword",
  keyword_low_rank: "Keyword",
  keyword_rank_drop: "Keyword",
};

export default function OpportunitiesPanel({ siteId }: { siteId: number }) {
  const router = useRouter();
  const [opportunities, setOpportunities] = useState<Opportunity[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getOpportunities(siteId)
      .then((data) => !cancelled && setOpportunities(data))
      .catch(() => !cancelled && setOpportunities([]));
    return () => {
      cancelled = true;
    };
  }, [siteId]);

  if (opportunities === null) {
    return null; // avoid a layout flash while the first load is in flight
  }

  if (opportunities.length === 0) {
    return (
      <div className="panel" style={{ padding: "16px 18px", marginBottom: 20 }}>
        <div className="pages-header" style={{ marginBottom: 0 }}>
          <h3>Opportunities</h3>
        </div>
        <div style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 8 }}>
          Nothing to fix right now — run an audit or track a keyword to surface recommendations here.
        </div>
      </div>
    );
  }

  return (
    <div className="panel" style={{ padding: "16px 18px", marginBottom: 20 }}>
      <div className="pages-header" style={{ marginBottom: 12 }}>
        <h3>Opportunities</h3>
        <span style={{ color: "var(--text-muted)", fontSize: 12.5 }}>
          {opportunities.length} thing{opportunities.length === 1 ? "" : "s"} to improve
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {opportunities.map((opp, i) => (
          <div
            key={i}
            className="clickable"
            onClick={() => router.push(`/sites/${siteId}/pages/${opp.page_id}`)}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              padding: "10px 12px",
              borderRadius: 6,
              border: "1px solid var(--border)",
              background: "var(--surface-raised)",
            }}
          >
            <span className={`status-pill ${SEVERITY_PILL[opp.severity]}`} style={{ flexShrink: 0, marginTop: 1 }}>
              {TYPE_LABEL[opp.type]}
            </span>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 500 }}>{opp.title}</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2, wordBreak: "break-word" }}>
                {opp.detail}
              </div>
              {opp.suggested_fix && (
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>→ {opp.suggested_fix}</div>
              )}
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, wordBreak: "break-all" }}>
                {opp.page_url}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
