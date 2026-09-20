"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { routes } from "@/lib/routes";
import type { KeywordMovement, ScoreMovement, SiteHealth } from "@/lib/types";
import ScoreTrendChart from "./ScoreTrendChart";

function pathOf(url: string): string {
  try {
    return new URL(url).pathname || "/";
  } catch {
    return url;
  }
}

export default function SiteHealthPanel({ siteId }: { siteId: number }) {
  const router = useRouter();
  const [health, setHealth] = useState<SiteHealth | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getSiteHealth(siteId)
      .then((data) => !cancelled && setHealth(data))
      .catch(() => !cancelled && setHealth(null));
    return () => {
      cancelled = true;
    };
  }, [siteId]);

  if (!health) return null;

  const hasMovements =
    health.score_wins.length > 0 ||
    health.score_losses.length > 0 ||
    health.keyword_wins.length > 0 ||
    health.keyword_losses.length > 0;

  function goToPage(pageId: number) {
    router.push(routes.page(siteId, pageId));
  }

  function ScoreRow({ m }: { m: ScoreMovement }) {
    const good = m.delta > 0;
    return (
      <div className="health-row" onClick={() => goToPage(m.page_id)}>
        <div className="health-label">
          {pathOf(m.page_url)}
          <div className="health-sub">
            {m.previous_score} → {m.new_score}
          </div>
        </div>
        <div className={`health-delta ${good ? "good" : "bad"}`}>
          {good ? "+" : ""}
          {m.delta}
        </div>
      </div>
    );
  }

  function KeywordRow({ m }: { m: KeywordMovement }) {
    const good = m.delta > 0;
    const from = m.previous_rank !== null ? `#${m.previous_rank}` : "not found";
    const to = m.new_rank !== null ? `#${m.new_rank}` : "not found";
    return (
      <div className="health-row" onClick={() => goToPage(m.page_id)}>
        <div className="health-label">
          &quot;{m.keyword}&quot;
          <div className="health-sub">
            {from} → {to}
          </div>
        </div>
        <div className={`health-delta ${good ? "good" : "bad"}`}>{good ? "↑" : "↓"}</div>
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 32 }}>
      <div className="section-toolbar">
        <div className="section-title">Site health</div>
      </div>

      <div className="panel health-panel" style={{ marginBottom: 10 }}>
        <div className="gauge-label" style={{ marginBottom: 10 }}>SCORE OVER TIME</div>
        <ScoreTrendChart trend={health.score_trend} />
      </div>

      {hasMovements && (
        <div className="card-grid" style={{ marginBottom: 0 }}>
          <div className="panel health-panel">
            <div className="gauge-label">RECENT WINS</div>
            {health.score_wins.length === 0 && health.keyword_wins.length === 0 ? (
              <div style={{ color: "var(--text-muted)", fontSize: 12.5, marginTop: 8 }}>Nothing yet.</div>
            ) : (
              <>
                {health.score_wins.length > 0 && (
                  <>
                    <div className="health-subtitle">Score</div>
                    {health.score_wins.map((m, i) => (
                      <ScoreRow m={m} key={i} />
                    ))}
                  </>
                )}
                {health.keyword_wins.length > 0 && (
                  <>
                    <div className="health-subtitle">Keywords</div>
                    {health.keyword_wins.map((m, i) => (
                      <KeywordRow m={m} key={i} />
                    ))}
                  </>
                )}
              </>
            )}
          </div>

          <div className="panel health-panel">
            <div className="gauge-label">RECENT LOSSES</div>
            {health.score_losses.length === 0 && health.keyword_losses.length === 0 ? (
              <div style={{ color: "var(--text-muted)", fontSize: 12.5, marginTop: 8 }}>Nothing yet.</div>
            ) : (
              <>
                {health.score_losses.length > 0 && (
                  <>
                    <div className="health-subtitle">Score</div>
                    {health.score_losses.map((m, i) => (
                      <ScoreRow m={m} key={i} />
                    ))}
                  </>
                )}
                {health.keyword_losses.length > 0 && (
                  <>
                    <div className="health-subtitle">Keywords</div>
                    {health.keyword_losses.map((m, i) => (
                      <KeywordRow m={m} key={i} />
                    ))}
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
