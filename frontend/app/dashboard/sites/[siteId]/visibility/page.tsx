"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Fragment, useCallback, useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDateTime } from "@/lib/format";
import { useSiteJobs } from "@/lib/use-site-jobs";
import JobProgress from "@/components/JobProgress";
import type {
  Site,
  VisibilityAdvice,
  VisibilityEngine,
  VisibilityEngineResult,
  VisibilityKeyword,
  VisibilityReport,
} from "@/lib/types";

const ENGINES: { key: VisibilityEngine; label: string; hint: string }[] = [
  { key: "google", label: "Google", hint: "Where you rank in the normal organic results" },
  { key: "google_ai_overview", label: "AI Overview", hint: "Whether Google's AI answer cites your site as a source" },
  { key: "chatgpt", label: "ChatGPT", hint: "Whether the model names your site when asked this question" },
];

export default function VisibilityPage() {
  const params = useParams<{ siteId: string }>();
  const siteId = Number(params.siteId);
  const { refresh: refreshUser } = useAuth();

  const [site, setSite] = useState<Site | null>(null);
  const [report, setReport] = useState<VisibilityReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [advising, setAdvising] = useState<string | null>(null);
  const [newKeyword, setNewKeyword] = useState("");
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    const [s, r] = await Promise.all([api.getSite(siteId), api.visibilityReport(siteId)]);
    setSite(s);
    setReport(r);
  }, [siteId]);

  const onFinish = useCallback(
    (kind: string) => {
      if (kind === "visibility") {
        load().catch(() => {});
        refreshUser();
      }
    },
    [load, refreshUser]
  );
  const { jobs } = useSiteJobs(siteId, onFinish);

  useEffect(() => {
    load().catch((e) => setError(e instanceof ApiError ? e.message : "Could not load visibility."));
  }, [load]);

  async function suggest(keyword: string) {
    setAdvising(keyword);
    setError(null);
    try {
      const advice = await api.suggestForKeyword(siteId, keyword);
      setReport((current) =>
        current
          ? { ...current, keywords: current.keywords.map((k) => (k.keyword === keyword ? { ...k, advice } : k)) }
          : current
      );
      setOpen(keyword);
      refreshUser();  // a credit was just spent
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not get suggestions.");
    } finally {
      setAdvising(null);
    }
  }

  async function addKeyword(e: FormEvent) {
    e.preventDefault();
    const keyword = newKeyword.trim();
    if (!keyword) return;
    setAdding(true);
    setError(null);
    try {
      await api.addSiteKeyword(siteId, keyword);
      setNewKeyword("");
      await load();  // it joins the table straight away, unchecked
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add that keyword.");
    } finally {
      setAdding(false);
    }
  }

  async function check() {
    setBusy(true);
    setError(null);
    try {
      await api.startVisibilityCheck(siteId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start the check.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !report) return <div className="form-error">{error}</div>;
  if (!report || !site) return <div className="loading-state">Loading…</div>;

  const job = jobs?.visibility ?? null;
  const cost = report.targeted_keywords * 2;

  return (
    <div>
      <div className="topbar">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="breadcrumb">
            <Link href={`/dashboard/sites/${siteId}`} className="link-btn">
              {site.domain}
            </Link>{" "}
            / Visibility
          </div>
          <h1 className="page-title">Search &amp; AI visibility</h1>
          <div className="page-sub">
            {report.checked_at ? `Last checked ${formatDateTime(report.checked_at)}` : "Not checked yet"}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Link className="btn btn-ghost" href={`/dashboard/sites/${siteId}/keywords`}>
            Keywords
          </Link>
          <button
            className="btn"
            onClick={check}
            disabled={busy || job?.status === "running" || report.targeted_keywords === 0}
          >
            {job?.status === "running" ? "Checking…" : "Check now"}
          </button>
        </div>
      </div>

      {error && <div className="form-error" style={{ marginBottom: 16 }}>{error}</div>}

      <form className="keyword-add" onSubmit={addKeyword}>
        <input
          type="text"
          placeholder="Add a keyword you want to rank for…"
          value={newKeyword}
          onChange={(e) => setNewKeyword(e.target.value)}
          aria-label="Add a keyword"
        />
        <button className="btn btn-sm" type="submit" disabled={adding || !newKeyword.trim()}>
          {adding ? "Adding…" : "Add keyword"}
        </button>
        <span className="admin-hint">
          Free to add — it costs credits only when you check it.
        </span>
      </form>

      {report.targeted_keywords === 0 ? (
        <div className="panel empty-state">
          Nothing tracked yet. Add a keyword above, or let Signal suggest some from your Search Console and your
          own pages.
          <div style={{ marginTop: 12 }}>
            <Link className="btn btn-ghost" href={`/dashboard/sites/${siteId}/keywords`}>
              Suggest keywords for me →
            </Link>
          </div>
        </div>
      ) : (
        <>
          <JobProgress
            job={job}
            idleHint={`Checks all ${report.targeted_keywords} targeted keyword${
              report.targeted_keywords === 1 ? "" : "s"
            } in Google and in an AI answer — ${cost} credits.`}
          />

          <div className="stat-row stat-row-4" style={{ marginTop: 20 }}>
            <div className="stat-cell">
              <div className="stat-label">Keywords tracked</div>
              <div className="stat-value">{report.targeted_keywords}</div>
            </div>
            <div className="stat-cell">
              <div className="stat-label">Ranking in Google</div>
              <div className="stat-value">{report.google_visible}</div>
              <div className="admin-hint">in the first 100 results</div>
            </div>
            <div className="stat-cell">
              <div className="stat-label">Cited by AI Overview</div>
              <div className="stat-value">{report.ai_overview_cited}</div>
              <div className="admin-hint">Google’s AI answer names you</div>
            </div>
            <div className="stat-cell">
              <div className="stat-label">Mentioned by ChatGPT</div>
              <div className="stat-value">{report.chatgpt_mentions}</div>
              <div className="admin-hint">asked as a question</div>
            </div>
          </div>

          <div className="panel pages-panel" style={{ marginTop: 20 }}>
            <div className="admin-scroll">
              <table className="admin-table visibility-table">
                <thead>
                  <tr>
                    <th>Keyword</th>
                    {ENGINES.map((e) => (
                      <th key={e.key} title={e.hint}>
                        {e.label}
                      </th>
                    ))}
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {report.keywords.map((row) => {
                    const byEngine = Object.fromEntries(row.engines.map((e) => [e.engine, e]));
                    const expanded = open === row.keyword;
                    return (
                      <Fragment key={row.keyword}>
                        <tr className={expanded ? "vis-row-open" : ""}>
                          <td className="keyword-name">{row.keyword}</td>
                          {ENGINES.map((engine) => (
                            <td key={engine.key}>
                              <EngineCell result={byEngine[engine.key]} engine={engine.key} />
                            </td>
                          ))}
                          <td className="num">
                            <KeywordAction
                              row={row}
                              expanded={expanded}
                              busy={advising === row.keyword}
                              onToggle={() => setOpen(expanded ? null : row.keyword)}
                              onGenerate={() => suggest(row.keyword)}
                            />
                          </td>
                        </tr>
                        {expanded && row.advice && (
                          <tr className="vis-advice-row">
                            <td colSpan={ENGINES.length + 2}>
                              <AdvicePanel
                                advice={row.advice}
                                busy={advising === row.keyword}
                                onRegenerate={() => suggest(row.keyword)}
                              />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <p className="admin-hint" style={{ marginTop: 14, maxWidth: 720, lineHeight: 1.6 }}>
            The ChatGPT column asks the model your keyword as a question and looks for your name in the answer.
            That tells you whether your brand has made it into what the model knows about this topic — it isn’t a
            claim about what ChatGPT would cite while browsing the web live.
          </p>
        </>
      )}
    </div>
  );
}

function EngineCell({ result, engine }: { result?: VisibilityEngineResult; engine: VisibilityEngine }) {
  if (!result) return <span className="muted">not checked</span>;

  if (result.present) {
    return (
      <span className="vis-yes" title={result.detail ?? undefined}>
        {engine === "google" && result.position ? `#${result.position}` : "Yes"}
      </span>
    );
  }
  // "Google showed no AI answer at all" is not the same failure as "it showed
  // one and picked someone else", and the difference is actionable.
  const neutral = result.detail?.startsWith("No AI Overview");
  return (
    <span className={neutral ? "muted" : "vis-no"} title={result.detail ?? undefined}>
      {neutral ? "no AI answer" : "No"}
      {result.detail?.startsWith("Cited instead") && (
        <span className="vis-instead">{result.detail.replace("Cited instead: ", "")}</span>
      )}
    </span>
  );
}


function KeywordAction({
  row,
  expanded,
  busy,
  onToggle,
  onGenerate,
}: {
  row: VisibilityKeyword;
  expanded: boolean;
  busy: boolean;
  onToggle: () => void;
  onGenerate: () => void;
}) {
  if (busy) return <span className="muted">Thinking…</span>;
  if (row.advice) {
    return (
      <button className="link-btn" onClick={onToggle}>
        {expanded ? "Hide" : "How to improve"}
        {row.advice.stale && !expanded && <span className="advice-stale-dot" title="Re-checked since this was written" />}
      </button>
    );
  }
  return (
    <button className="link-btn" onClick={onGenerate} title="1 credit — the search itself is already paid for">
      How to improve
    </button>
  );
}

function AdvicePanel({
  advice,
  busy,
  onRegenerate,
}: {
  advice: VisibilityAdvice;
  busy: boolean;
  onRegenerate: () => void;
}) {
  return (
    <div className="advice">
      {advice.stale && (
        <div className="advice-stale">
          This keyword has been checked again since these suggestions were written, so they may describe a
          search that has moved on.{" "}
          <button className="link-btn" onClick={onRegenerate} disabled={busy}>
            Get fresh suggestions
          </button>
        </div>
      )}
      <p className="advice-diagnosis">{advice.diagnosis}</p>

      {advice.actions.length > 0 && (
        <ol className="advice-actions">
          {advice.actions.map((action, i) => (
            <li key={i}>
              <div className="advice-action-head">
                <span className="advice-action-title">{action.title}</span>
                <span className={`advice-tag ${action.addresses}`}>
                  {action.addresses === "google" ? "Google" : action.addresses === "ai" ? "AI answers" : "both"}
                </span>
              </div>
              {action.detail && <p className="advice-action-detail">{action.detail}</p>}
            </li>
          ))}
        </ol>
      )}

      <div className="advice-foot">
        {advice.target_page_url ? (
          <span>
            Page to change: <a href={advice.target_page_url} target="_blank" rel="noopener noreferrer">{advice.target_page_url}</a>
          </span>
        ) : (
          <span>No existing page fits this keyword — the suggestions describe a new one.</span>
        )}
        <button className="link-btn" onClick={onRegenerate} disabled={busy}>
          Regenerate (1 credit)
        </button>
      </div>
      <p className="advice-caveat">
        Written by a language model from what Signal measured for this exact search — the pages that outrank you,
        what the AI answers cited, and your own page&apos;s content. Suggestions, not guarantees.
      </p>
    </div>
  );
}
