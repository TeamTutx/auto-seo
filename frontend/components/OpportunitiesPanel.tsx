"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Opportunity, OpportunitySeverity } from "@/lib/types";

const SEVERITY_ORDER: OpportunitySeverity[] = ["high", "medium", "low"];
const SEVERITY_LABEL: Record<OpportunitySeverity, string> = { high: "High", medium: "Medium", low: "Low" };

export default function OpportunitiesPanel({ siteId }: { siteId: number }) {
  const router = useRouter();
  const [opportunities, setOpportunities] = useState<Opportunity[] | null>(null);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [filter, setFilter] = useState<"all" | OpportunitySeverity>("all");
  const [bulkAction, setBulkAction] = useState<"collapse" | "expand">("collapse");

  useEffect(() => {
    let cancelled = false;
    api
      .getOpportunities(siteId)
      .then((data) => {
        if (cancelled) return;
        setOpportunities(data);
        setExpanded(Object.fromEntries(data.map((o, i) => [i, o.severity === "high"])));
      })
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
      <div className="panel" style={{ padding: "16px 18px", marginBottom: 32 }}>
        <div className="section-title" style={{ marginBottom: 0 }}>Opportunities</div>
        <div style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 8 }}>
          Nothing to fix right now — run an audit or track a keyword to surface recommendations here.
        </div>
      </div>
    );
  }

  const counts = SEVERITY_ORDER.map((sev) => ({
    sev,
    count: opportunities.filter((o) => o.severity === sev).length,
  })).filter((c) => c.count > 0);

  function toggleCard(i: number) {
    setExpanded((prev) => ({ ...prev, [i]: !prev[i] }));
  }

  function handleBulkToggle() {
    const collapsing = bulkAction === "collapse";
    const next: Record<number, boolean> = {};
    opportunities!.forEach((o, i) => {
      if (filter !== "all" && o.severity !== filter) {
        next[i] = expanded[i]; // leave filtered-out cards untouched
        return;
      }
      next[i] = !collapsing;
    });
    setExpanded(next);
    setBulkAction(collapsing ? "expand" : "collapse");
  }

  return (
    <div style={{ marginBottom: 32 }}>
      <div className="section-toolbar">
        <div className="section-title">Opportunities</div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div className="chip-row">
            <button className={`chip${filter === "all" ? " active" : ""}`} onClick={() => setFilter("all")}>
              All · {opportunities.length}
            </button>
            {counts.map(({ sev, count }) => (
              <button key={sev} className={`chip${filter === sev ? " active" : ""}`} onClick={() => setFilter(sev)}>
                {SEVERITY_LABEL[sev]} · {count}
              </button>
            ))}
          </div>
          <button className="toolbar-btn" onClick={handleBulkToggle}>
            {bulkAction === "collapse" ? "Collapse all" : "Expand all"}
          </button>
        </div>
      </div>

      <div className="card-grid" style={{ marginBottom: 0 }}>
        {opportunities.map((opp, i) => {
          if (filter !== "all" && opp.severity !== filter) return null;
          const isOpen = Boolean(expanded[i]);
          return (
            <div className={`check-card${isOpen ? " open" : ""}`} key={i}>
              <button className="check-head" onClick={() => toggleCard(i)}>
                <span className={`sev-pill ${opp.severity}`}>{SEVERITY_LABEL[opp.severity]}</span>
                <div className="check-head-body">
                  <div className="check-title">{opp.title}</div>
                  <div className="check-summary">{opp.detail}</div>
                </div>
                <div className="chevron">▾</div>
              </button>

              {isOpen && (
                <div className="check-card-content">
                  {opp.suggested_fix && <div className="check-fix">{opp.suggested_fix}</div>}
                  <a
                    className="check-goto"
                    onClick={(e) => {
                      e.preventDefault();
                      router.push(`/sites/${siteId}/pages/${opp.page_id}`);
                    }}
                    href={`/sites/${siteId}/pages/${opp.page_id}`}
                  >
                    {opp.page_url} →
                  </a>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
