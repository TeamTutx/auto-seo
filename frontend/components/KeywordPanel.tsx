"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { LOCATION_OPTIONS, type CompetitorResult, type KeywordRank } from "@/lib/types";
import RankHistoryChart from "./RankHistoryChart";

type DetailTab = "history" | "competitors";

export default function KeywordPanel({ pageId }: { pageId: number }) {
  const [keywords, setKeywords] = useState<KeywordRank[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [locationCode, setLocationCode] = useState(2356);
  const [device, setDevice] = useState("desktop");
  const [submitting, setSubmitting] = useState(false);
  const [rechecking, setRechecking] = useState(false);

  const [expanded, setExpanded] = useState<string | null>(null);
  const [tab, setTab] = useState<DetailTab>("history");
  const [historyCache, setHistoryCache] = useState<Record<string, KeywordRank[]>>({});
  const [competitorsCache, setCompetitorsCache] = useState<Record<string, CompetitorResult[]>>({});
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

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
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not recheck rankings.");
    } finally {
      setRechecking(false);
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
  }

  return (
    <div className="panel side-panel" style={{ marginTop: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <h4 style={{ marginBottom: 0 }}>Target keywords</h4>
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
        <form onSubmit={handleAdd} style={{ marginBottom: 12, display: "flex", flexDirection: "column", gap: 6 }}>
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
            }}
          />
          <div style={{ display: "flex", gap: 6 }}>
            <select
              value={locationCode}
              onChange={(e) => setLocationCode(Number(e.target.value))}
              style={{
                flex: 1,
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
          </div>
          <button className="btn" type="submit" disabled={submitting || !keyword.trim()} style={{ fontSize: 12 }}>
            Track
          </button>
        </form>
      )}

      {keywords === null ? (
        <div style={{ color: "var(--text-muted)", fontSize: 12.5 }}>Loading…</div>
      ) : keywords.length === 0 ? (
        <div style={{ color: "var(--text-muted)", fontSize: 12.5 }}>No keywords tracked yet.</div>
      ) : (
        keywords.map((kw) => (
          <div key={kw.id}>
            <div className="kw-row" style={{ cursor: "pointer" }} onClick={() => toggleExpand(kw)}>
              <span>{kw.keyword}</span>
              <span className="kw-rank">{kw.rank_position !== null ? `#${kw.rank_position}` : "Not found"}</span>
            </div>

            {expanded === kw.keyword && (
              <div style={{ padding: "8px 0 14px 0", borderBottom: "1px solid var(--border)" }}>
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
              </div>
            )}
          </div>
        ))
      )}

      {keywords && keywords.length > 0 && (
        <button
          className="btn btn-ghost"
          style={{ width: "100%", marginTop: 14, fontSize: 12.5 }}
          onClick={handleRecheck}
          disabled={rechecking}
        >
          {rechecking ? "Rechecking…" : "Recheck rankings now"}
        </button>
      )}
    </div>
  );
}
