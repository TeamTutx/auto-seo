"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { routes, useRouteId } from "@/lib/routes";
import { useAuth } from "@/lib/auth-context";
import { useSiteJobs } from "@/lib/use-site-jobs";
import JobProgress from "@/components/JobProgress";
import type { KeywordIdea, Site } from "@/lib/types";

const SOURCE_LABEL: Record<KeywordIdea["source"], { label: string; title: string }> = {
  gsc: { label: "Search Console", title: "Measured: Google already shows your site for this" },
  ai: { label: "From your page", title: "Suggested by reading your page's content" },
  serp: { label: "Related search", title: "Google suggests this alongside your other keywords" },
  manual: { label: "You added it", title: "Typed in by hand rather than suggested by Signal" },
};

function KeywordsPage() {
  const siteId = useRouteId("id");
  const { refresh: refreshUser } = useAuth();

  const [site, setSite] = useState<Site | null>(null);
  const [ideas, setIdeas] = useState<KeywordIdea[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [s, list] = await Promise.all([api.getSite(siteId), api.keywordIdeas(siteId)]);
    setSite(s);
    setIdeas(list);
  }, [siteId]);

  const onFinish = useCallback(
    (kind: string) => {
      if (kind === "keywords") {
        load().catch(() => {});
        refreshUser();
      }
    },
    [load, refreshUser]
  );
  const { jobs } = useSiteJobs(siteId, onFinish);

  useEffect(() => {
    load().catch((e) => setError(e instanceof ApiError ? e.message : "Could not load keywords."));
  }, [load]);

  async function discover() {
    setBusy(true);
    setError(null);
    try {
      await api.discoverKeywords(siteId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start.");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(idea: KeywordIdea) {
    setIdeas((current) =>
      current?.map((i) => (i.id === idea.id ? { ...i, targeted: !i.targeted } : i)) ?? current
    );
    try {
      setIdeas(await api.targetKeywords(siteId, [idea.id], !idea.targeted));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save that.");
      load().catch(() => {});
    }
  }

  async function remove(idea: KeywordIdea) {
    setIdeas((current) => current?.filter((i) => i.id !== idea.id) ?? current);
    try {
      await api.deleteKeywordIdea(siteId, idea.id);
    } catch {
      load().catch(() => {});
    }
  }

  if (error && !ideas) return <div className="form-error">{error}</div>;
  if (!ideas || !site) return <div className="loading-state">Loading…</div>;

  const job = jobs?.keywords ?? null;
  const targeted = ideas.filter((i) => i.targeted).length;

  return (
    <div>
      <div className="topbar">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="breadcrumb">
            <Link href={routes.site(siteId)} className="link-btn">
              {site.domain}
            </Link>{" "}
            / Keywords
          </div>
          <h1 className="page-title">Keywords</h1>
          <div className="page-sub">
            {ideas.length} idea{ideas.length === 1 ? "" : "s"} · {targeted} you’re targeting
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {targeted > 0 && (
            <Link className="btn btn-ghost" href={routes.siteVisibility(siteId)}>
              Check visibility →
            </Link>
          )}
          <button className="btn" onClick={discover} disabled={busy || job?.status === "running"}>
            {job?.status === "running" ? "Finding…" : ideas.length ? "Find more" : "Find keywords"}
          </button>
        </div>
      </div>

      {error && <div className="form-error" style={{ marginBottom: 16 }}>{error}</div>}

      <JobProgress
        job={job}
        idleHint="Signal reads your Search Console, your home page and Google's related searches to suggest keywords. Up to 2 credits."
      />

      {ideas.length === 0 ? (
        <div className="panel empty-state" style={{ marginTop: 20 }}>
          No keyword ideas yet. “Find keywords” reads your home page and, if you’ve connected Google, the searches
          your site already appears for.
        </div>
      ) : (
        <div className="panel pages-panel" style={{ marginTop: 20 }}>
          <div className="admin-scroll">
            <table className="admin-table keyword-table">
              <thead>
                <tr>
                  <th style={{ width: 44 }}>Target</th>
                  <th>Keyword</th>
                  <th>Where it came from</th>
                  <th className="num" style={{ textAlign: "right" }}>
                    Impressions
                  </th>
                  <th className="num" style={{ textAlign: "right" }}>
                    Position
                  </th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {ideas.map((idea) => (
                  <tr key={idea.id} className={idea.targeted ? "targeted" : ""}>
                    <td>
                      <input
                        type="checkbox"
                        checked={idea.targeted}
                        onChange={() => toggle(idea)}
                        aria-label={`Target ${idea.keyword}`}
                      />
                    </td>
                    <td>
                      <div className="keyword-name">{idea.keyword}</div>
                      {idea.rationale && <div className="keyword-why">{idea.rationale}</div>}
                    </td>
                    <td>
                      <span className={`source-tag ${idea.source}`} title={SOURCE_LABEL[idea.source].title}>
                        {SOURCE_LABEL[idea.source].label}
                      </span>
                    </td>
                    <td className="num">{idea.impressions?.toLocaleString() ?? <span className="muted">—</span>}</td>
                    <td className="num">
                      {idea.position !== null ? (
                        idea.position.toFixed(1)
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td className="num">
                      <button className="link-btn" onClick={() => remove(idea)} style={{ color: "var(--text-muted)" }}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="admin-hint" style={{ marginTop: 14, maxWidth: 680, lineHeight: 1.6 }}>
        Only Search Console ideas come with real numbers — those are searches Google has already shown your site
        for. The others are suggestions, not traffic estimates: Signal doesn’t have a search-volume database and
        won’t invent one.
      </p>
    </div>
  );
}

// useSearchParams has to sit inside a Suspense boundary or `next build` fails
// (see CLAUDE.md). Same shape as /login, which has always read its query string.
export default function Page() {
  return (
    <Suspense fallback={<div className="loading-state">Loading…</div>}>
      <KeywordsPage />
    </Suspense>
  );
}
