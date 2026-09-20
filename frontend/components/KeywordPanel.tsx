"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useGeneratedResults } from "@/lib/use-generated-results";
import { LOCATION_OPTIONS, type CompetitorResult, type KeywordOpportunity, type KeywordRank } from "@/lib/types";
import RankHistoryChart from "./RankHistoryChart";

type DetailTab = "history" | "competitors" | "opportunities" | "action-plan";

const LOW_RANK_THRESHOLD = 10; // matches the backend's opportunities service

function needsActionPlan(kw: KeywordRank): boolean {
  return kw.rank_position === null || kw.rank_position > LOW_RANK_THRESHOLD;
}

export default function KeywordPanel({ pageId }: { pageId: number }) {
  const [keywords, setKeywords] = useState<KeywordRank[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [locationCode, setLocationCode] = useState(2356);
  const [device, setDevice] = useState("desktop");
  const [submitting, setSubmitting] = useState(false);
  const [rechecking, setRechecking] = useState(false);
  const [deletingKeyword, setDeletingKeyword] = useState<string | null>(null);

  const [expanded, setExpanded] = useState<string | null>(null);
  const [tab, setTab] = useState<DetailTab | null>(null);
  const [historyCache, setHistoryCache] = useState<Record<string, KeywordRank[]>>({});
  const [competitorsCache, setCompetitorsCache] = useState<Record<string, CompetitorResult[]>>({});
  const [opportunitiesCache, setOpportunitiesCache] = useState<Record<string, KeywordOpportunity[]>>({});
  const [actionPlanCache, setActionPlanCache] = useState<Record<string, string>>({});
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [addingOpportunity, setAddingOpportunity] = useState<string | null>(null);
  const [addedOpportunities, setAddedOpportunities] = useState<Set<string>>(new Set());

  // Competitor lookups, opportunity lists and action plans all cost credits.
  // Seed the caches from what has already been bought so reopening a keyword
  // after a refresh shows the answer instead of charging for it again.
  const stored = useGeneratedResults(pageId);
  useEffect(() => {
    if (!stored) return;
    const pick = <T,>(kind: string): Record<string, T> =>
      Object.fromEntries(
        Object.entries(stored)
          .filter(([key]) => key.startsWith(`${kind}::`))
          .map(([key, payload]) => [key.slice(kind.length + 2), payload as T])
      );

    const competitors = pick<CompetitorResult[]>("competitors");
    const opportunities = pick<KeywordOpportunity[]>("keyword_opportunities");
    const plans = pick<{ plan: string }>("action_plan");

    // Anything generated in this session wins - it is newer than what loaded.
    if (Object.keys(competitors).length) setCompetitorsCache((c) => ({ ...competitors, ...c }));
    if (Object.keys(opportunities).length) setOpportunitiesCache((c) => ({ ...opportunities, ...c }));
    if (Object.keys(plans).length) {
      setActionPlanCache((c) => ({
        ...Object.fromEntries(Object.entries(plans).map(([kw, p]) => [kw, p.plan])),
        ...c,
      }));
    }
  }, [stored]);

  async function load() {
    try {
      setKeywords(await api.listKeywords(pageId));
    } catch {
      setKeywords([]);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageId]);

  async function handleAdd(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.addKeyword(pageId, keyword.trim(), locationCode, device);
      setKeyword("");
      setAdding(false);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not track keyword.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRecheck() {
    setError(null);
    setRechecking(true);
    try {
      await api.recheckKeywords(pageId);
      setHistoryCache({});
      setCompetitorsCache({});
      setOpportunitiesCache({});
      setActionPlanCache({});
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not recheck rankings.");
    } finally {
      setRechecking(false);
    }
  }

  async function handleDelete(kw: KeywordRank) {
    if (!confirm(`Stop tracking "${kw.keyword}"? This removes its rank history.`)) return;
    setError(null);
    setDeletingKeyword(kw.keyword);
    try {
      await api.deleteKeyword(pageId, kw.keyword);
      if (expanded === kw.keyword) setExpanded(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete keyword.");
    } finally {
      setDeletingKeyword(null);
    }
  }

  async function toggleExpand(kw: KeywordRank) {
    if (expanded === kw.keyword) {
      setExpanded(null);
      return;
    }
    setExpanded(kw.keyword);
    setTab("history");
    setDetailError(null);
    if (!historyCache[kw.keyword]) {
      setDetailLoading(true);
      try {
        const history = await api.keywordHistory(pageId, kw.keyword);
        setHistoryCache((prev) => ({ ...prev, [kw.keyword]: history }));
      } catch (err) {
        setDetailError(err instanceof ApiError ? err.message : "Could not load history.");
      } finally {
        setDetailLoading(false);
      }
    }
  }

  async function showTab(kw: KeywordRank, nextTab: DetailTab) {
    if (tab === nextTab) {
      setTab(null); // clicking the active tab again collapses it
      return;
    }
    setTab(nextTab);
    setDetailError(null);
    if (nextTab === "competitors" && !competitorsCache[kw.keyword]) {
      setDetailLoading(true);
      try {
        const competitors = await api.getCompetitors(pageId, kw.keyword, kw.location_code, kw.device);
        setCompetitorsCache((prev) => ({ ...prev, [kw.keyword]: competitors }));
      } catch (err) {
        setDetailError(err instanceof ApiError ? err.message : "Could not load competitors.");
      } finally {
        setDetailLoading(false);
      }
    }
    if (nextTab === "opportunities" && !opportunitiesCache[kw.keyword]) {
      setDetailLoading(true);
      try {
        const opportunities = await api.getKeywordOpportunities(pageId, kw.keyword, kw.location_code, kw.device);
        setOpportunitiesCache((prev) => ({ ...prev, [kw.keyword]: opportunities }));
      } catch (err) {
        setDetailError(err instanceof ApiError ? err.message : "Could not load keyword opportunities.");
      } finally {
        setDetailLoading(false);
      }
    }
    if (nextTab === "action-plan" && !actionPlanCache[kw.keyword]) {
      setDetailLoading(true);
      try {
        const { plan } = await api.getRankingActionPlan(pageId, kw.keyword, kw.location_code, kw.device);
        setActionPlanCache((prev) => ({ ...prev, [kw.keyword]: plan }));
      } catch (err) {
        setDetailError(err instanceof ApiError ? err.message : "Could not load an action plan.");
      } finally {
        setDetailLoading(false);
      }
    }
  }

  async function handleAddOpportunity(opportunityKeyword: string) {
    setAddingOpportunity(opportunityKeyword);
    try {
      await api.addKeyword(pageId, opportunityKeyword, locationCode, device);
      setAddedOpportunities((prev) => new Set(prev).add(opportunityKeyword));
      await load();
    } catch (err) {
      setDetailError(err instanceof ApiError ? err.message : "Could not add keyword.");
    } finally {
      setAddingOpportunity(null);
    }
  }

  return (
    <div>
      <div className="section-toolbar">
        <div className="section-title">Target keywords</div>
        <button
          className="btn-ghost btn"
          style={{ fontSize: 11.5, padding: "5px 10px" }}
          onClick={() => setAdding((v) => !v)}
        >
          {adding ? "Cancel" : "+ Add"}
        </button>
      </div>

      {error && (
        <div className="form-error" style={{ fontSize: 12, padding: "8px 10px" }}>
          {error}
        </div>
      )}

      {adding && (
        <form onSubmit={handleAdd} style={{ marginBottom: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            autoFocus
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="target keyword"
            style={{
              background: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "7px 9px",
              color: "var(--text)",
              fontSize: 12.5,
              flex: 1,
              minWidth: 160,
            }}
          />
          <select
            value={locationCode}
            onChange={(e) => setLocationCode(Number(e.target.value))}
            style={{
              background: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "7px 9px",
              color: "var(--text)",
              fontSize: 12,
            }}
          >
            {LOCATION_OPTIONS.map((opt) => (
              <option key={opt.code} value={opt.code}>
                {opt.label}
              </option>
            ))}
          </select>
          <select
            value={device}
            onChange={(e) => setDevice(e.target.value)}
            style={{
              background: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "7px 9px",
              color: "var(--text)",
              fontSize: 12,
            }}
          >
            <option value="desktop">Desktop</option>
            <option value="mobile">Mobile</option>
          </select>
          <button className="btn" type="submit" disabled={submitting || !keyword.trim()} style={{ fontSize: 12 }}>
            Track
          </button>
        </form>
      )}

      {keywords === null ? (
        <div className="loading-state">Loading…</div>
      ) : keywords.length === 0 ? (
        <div className="empty-state">No keywords tracked yet.</div>
      ) : (
        <div className="panel pages-panel">
          {keywords.map((kw) => (
            <div key={kw.id}>
              <div
                className={`tracked-kw-row${expanded === kw.keyword ? " open" : ""}`}
                onClick={() => toggleExpand(kw)}
              >
                <div className="kw-name">{kw.keyword}</div>
                <div className="kw-rank">{kw.rank_position !== null ? `#${kw.rank_position}` : "Not found"}</div>
                <div className="kw-chevron">▾</div>
                <button
                  className="kw-delete"
                  title="Stop tracking this keyword"
                  aria-label="Stop tracking this keyword"
                  disabled={deletingKeyword === kw.keyword}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(kw);
                  }}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 6h18"></path>
                    <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path>
                    <line x1="10" y1="11" x2="10" y2="17"></line>
                    <line x1="14" y1="11" x2="14" y2="17"></line>
                  </svg>
                </button>
              </div>

              {expanded === kw.keyword && (
                <div className="kw-detail">
                  <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
                    <button
                      className={tab === "history" ? "btn" : "btn-ghost btn"}
                      style={{ fontSize: 11, padding: "4px 10px" }}
                      onClick={() => showTab(kw, "history")}
                    >
                      History
                    </button>
                    <button
                      className={tab === "competitors" ? "btn" : "btn-ghost btn"}
                      style={{ fontSize: 11, padding: "4px 10px" }}
                      onClick={() => showTab(kw, "competitors")}
                    >
                      Competitors
                    </button>
                    <button
                      className={tab === "opportunities" ? "btn" : "btn-ghost btn"}
                      style={{ fontSize: 11, padding: "4px 10px" }}
                      onClick={() => showTab(kw, "opportunities")}
                    >
                      Opportunities
                    </button>
                    {needsActionPlan(kw) && (
                      <button
                        className={tab === "action-plan" ? "btn" : "btn-ghost btn"}
                        style={{ fontSize: 11, padding: "4px 10px" }}
                        onClick={() => showTab(kw, "action-plan")}
                      >
                        Action plan
                      </button>
                    )}
                  </div>

                  {detailLoading && <div style={{ color: "var(--text-muted)", fontSize: 12 }}>Loading…</div>}
                  {detailError && <div style={{ color: "var(--bad)", fontSize: 12 }}>{detailError}</div>}

                  {!detailLoading && !detailError && tab === "history" && historyCache[kw.keyword] && (
                    <RankHistoryChart history={historyCache[kw.keyword]} />
                  )}

                  {!detailLoading && !detailError && tab === "competitors" && competitorsCache[kw.keyword] && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {competitorsCache[kw.keyword].length === 0 ? (
                        <div style={{ color: "var(--text-muted)", fontSize: 12 }}>No competitors found.</div>
                      ) : (
                        competitorsCache[kw.keyword].map((c) => (
                          <a
                            key={c.position}
                            href={c.url}
                            target="_blank"
                            rel="noreferrer"
                            style={{ fontSize: 12, color: "var(--text)", textDecoration: "none" }}
                          >
                            <span style={{ color: "var(--accent)", fontFamily: "var(--font-display)" }}>
                              #{c.position}
                            </span>{" "}
                            {c.domain}
                          </a>
                        ))
                      )}
                    </div>
                  )}

                  {!detailLoading && !detailError && tab === "opportunities" && opportunitiesCache[kw.keyword] && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {opportunitiesCache[kw.keyword].length === 0 ? (
                        <div style={{ color: "var(--text-muted)", fontSize: 12 }}>
                          No keyword opportunities found.
                        </div>
                      ) : (
                        opportunitiesCache[kw.keyword].map((opp) => {
                          const alreadyTracked =
                            addedOpportunities.has(opp.keyword) ||
                            keywords?.some((k) => k.keyword.toLowerCase() === opp.keyword.toLowerCase());
                          return (
                            <div
                              key={opp.keyword}
                              style={{
                                padding: "8px 10px",
                                borderRadius: 6,
                                border: "1px solid var(--border)",
                                background: "var(--surface-raised)",
                              }}
                            >
                              <div style={{ fontSize: 12.5, color: "var(--text)", fontWeight: 500 }}>
                                {opp.keyword}
                              </div>
                              {opp.reason && (
                                <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 2 }}>
                                  {opp.reason}
                                </div>
                              )}
                              <button
                                className="btn-ghost btn"
                                style={{ fontSize: 11, padding: "4px 9px", marginTop: 6 }}
                                disabled={alreadyTracked || addingOpportunity === opp.keyword}
                                onClick={() => handleAddOpportunity(opp.keyword)}
                              >
                                {alreadyTracked
                                  ? "Tracking"
                                  : addingOpportunity === opp.keyword
                                  ? "Adding…"
                                  : "+ Add to tracking"}
                              </button>
                            </div>
                          );
                        })
                      )}
                    </div>
                  )}

                  {!detailLoading && !detailError && tab === "action-plan" && actionPlanCache[kw.keyword] && (
                    <div
                      style={{
                        padding: "10px 12px",
                        background: "var(--surface-raised)",
                        border: "1px solid var(--border)",
                        borderRadius: 6,
                        fontSize: 12.5,
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      {actionPlanCache[kw.keyword]}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          <div style={{ padding: "14px 18px" }}>
            <button
              className="btn btn-ghost"
              style={{ width: "100%", fontSize: 12.5 }}
              onClick={handleRecheck}
              disabled={rechecking}
            >
              {rechecking ? "Rechecking…" : "Recheck rankings now"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
