"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDateTime } from "@/lib/format";
import { useSiteJobs } from "@/lib/use-site-jobs";
import JobProgress from "@/components/JobProgress";
import type { Site, VisibilityEngine, VisibilityEngineResult, VisibilityReport } from "@/lib/types";

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

      {report.targeted_keywords === 0 ? (
        <div className="panel empty-state">
          Pick the keywords you want to rank for first — then Signal can check whether you show up for them.
          <div style={{ marginTop: 12 }}>
            <Link className="btn" href={`/dashboard/sites/${siteId}/keywords`}>
              Choose keywords →
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
                  </tr>
                </thead>
                <tbody>
                  {report.keywords.map((row) => {
                    const byEngine = Object.fromEntries(row.engines.map((e) => [e.engine, e]));
                    return (
                      <tr key={row.keyword}>
                        <td className="keyword-name">{row.keyword}</td>
                        {ENGINES.map((engine) => (
                          <td key={engine.key}>
                            <EngineCell result={byEngine[engine.key]} engine={engine.key} />
                          </td>
                        ))}
                      </tr>
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
