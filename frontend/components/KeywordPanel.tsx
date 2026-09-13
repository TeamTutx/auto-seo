"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import type { KeywordRank } from "@/lib/types";

export default function KeywordPanel({ pageId }: { pageId: number }) {
  const [keywords, setKeywords] = useState<KeywordRank[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [rechecking, setRechecking] = useState(false);

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
      await api.addKeyword(pageId, keyword.trim());
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
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not recheck rankings.");
    } finally {
      setRechecking(false);
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
        <form onSubmit={handleAdd} style={{ marginBottom: 12, display: "flex", gap: 6 }}>
          <input
            autoFocus
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="target keyword"
            style={{
              flex: 1,
              minWidth: 0,
              background: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "7px 9px",
              color: "var(--text)",
              fontSize: 12.5,
            }}
          />
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
          <div className="kw-row" key={kw.id}>
            <span>{kw.keyword}</span>
            <span className="kw-rank">{kw.rank_position !== null ? `#${kw.rank_position}` : "Not found"}</span>
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
