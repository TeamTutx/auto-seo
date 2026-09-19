"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { SearchPresence, TrendPoint } from "@/lib/types";

/** The site page's headline: how visible this site is in Google, how visible it
 *  is in AI answers, and what the home page's search traffic has been doing.
 *
 *  Everything animates in once on mount — gauges sweep up from zero, the trend
 *  line draws itself — because these are the numbers the page exists to show and
 *  motion is what makes the eye land on them. It runs once, not on a loop:
 *  a dashboard that keeps moving is a dashboard you stop reading. */
export default function SearchPresencePanel({ siteId }: { siteId: number }) {
  const [data, setData] = useState<SearchPresence | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .searchPresence(siteId)
      .then((d) => !cancelled && setData(d))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [siteId]);

  if (failed) return null;
  if (!data) {
    return (
      <div className="panel presence-panel">
        <div className="gauge-label">SEARCH PRESENCE</div>
        <div className="presence-skeleton" />
      </div>
    );
  }

  const neverChecked = data.checked_keywords === 0;

  return (
    <div className="panel presence-panel">
      <div className="presence-head">
        <div className="gauge-label">SEARCH PRESENCE</div>
        {data.last_checked_at && (
          <Link href={`/dashboard/sites/${siteId}/visibility`} className="link-btn">
            Full report →
          </Link>
        )}
      </div>

      <div className="presence-body">
        <div className="presence-gauges">
          <Gauge
            label="Google"
            hint={
              neverChecked
                ? "not checked yet"
                : `${data.google_visible} of ${data.checked_keywords} keyword${data.checked_keywords === 1 ? "" : "s"}`
            }
            score={data.google_score}
            footnote={data.best_position ? `best #${data.best_position}` : undefined}
            tone="google"
            delay={0}
          />
          <Gauge
            label="AI answers"
            hint={
              neverChecked
                ? "not checked yet"
                : `${data.ai_visible} of ${data.checked_keywords} keyword${data.checked_keywords === 1 ? "" : "s"}`
            }
            score={data.ai_score}
            footnote={
              neverChecked
                ? undefined
                : `${data.ai_overview_cited} AI Overview · ${data.chatgpt_mentions} ChatGPT`
            }
            tone="ai"
            delay={180}
          />
        </div>

        <div className="presence-trend">
          {data.trend.length > 0 ? (
            <>
              <div className="presence-trend-head">
                <div>
                  <div className="presence-trend-title">Search impressions</div>
                  <div className="presence-trend-sub">
                    {data.trend_page_url ? prettyPath(data.trend_page_url) : ""} · last 28 days
                  </div>
                </div>
                <div className="presence-figures">
                  <Figure value={data.impressions_total.toLocaleString()} label="impressions" change={data.impressions_change} />
                  <Figure value={data.clicks_total.toLocaleString()} label="clicks" change={data.clicks_change} />
                  {data.average_position && <Figure value={`#${data.average_position}`} label="avg position" />}
                </div>
              </div>
              <TrendChart points={data.trend} />
            </>
          ) : (
            <TrendEmpty reason={data.trend_unavailable} siteId={siteId} />
          )}
        </div>
      </div>

      {neverChecked && (
        <div className="presence-cta">
          {data.targeted_keywords === 0
            ? "Pick the keywords you want to rank for, then Signal can measure whether you show up."
            : `${data.targeted_keywords} keyword${data.targeted_keywords === 1 ? "" : "s"} targeted — run a check to fill these in.`}
          <Link
            className="btn btn-sm"
            href={`/dashboard/sites/${siteId}/${data.targeted_keywords === 0 ? "keywords" : "visibility"}`}
          >
            {data.targeted_keywords === 0 ? "Choose keywords" : "Check visibility"}
          </Link>
        </div>
      )}
    </div>
  );
}

const RADIUS = 46;
const CIRCUM = 2 * Math.PI * RADIUS;
// Three-quarters of a circle: an open arc reads as a gauge, a closed ring reads
// as a pie and invites comparing the two halves rather than each to 100%.
const SWEEP = 0.75;

function Gauge({
  label,
  hint,
  score,
  footnote,
  tone,
  delay,
}: {
  label: string;
  hint: string;
  score: number | null;
  footnote?: string;
  tone: "google" | "ai";
  delay: number;
}) {
  const shown = useCountUp(score ?? 0, delay, score !== null);
  const filled = CIRCUM * SWEEP * ((score ?? 0) / 100);

  return (
    <div className="gauge-card">
      <svg viewBox="0 0 120 120" className="gauge-svg" role="img" aria-label={`${label}: ${score ?? "not checked"}`}>
        <circle
          cx="60" cy="60" r={RADIUS} fill="none" stroke="var(--border)" strokeWidth="9" strokeLinecap="round"
          strokeDasharray={`${CIRCUM * SWEEP} ${CIRCUM}`}
          transform="rotate(135 60 60)"
        />
        {score !== null && (
          <circle
            cx="60" cy="60" r={RADIUS} fill="none" strokeWidth="9" strokeLinecap="round"
            stroke={tone === "google" ? "var(--accent)" : "var(--warn)"}
            strokeDasharray={`${filled} ${CIRCUM}`}
            transform="rotate(135 60 60)"
            className="gauge-arc"
            style={{ animationDelay: `${delay}ms`, ["--arc-len" as string]: `${filled}` }}
          />
        )}
      </svg>
      <div className="gauge-centre">
        <div className="gauge-pct">{score === null ? "—" : `${shown}%`}</div>
        <div className="gauge-name">{label}</div>
      </div>
      <div className="gauge-hint">{hint}</div>
      {footnote && <div className="gauge-foot">{footnote}</div>}
    </div>
  );
}

function Figure({ value, label, change }: { value: string; label: string; change?: number | null }) {
  return (
    <div className="presence-figure">
      <div className="presence-figure-value">
        {value}
        {typeof change === "number" && (
          <span className={change > 0 ? "pos" : change < 0 ? "neg" : "muted"}>
            {change > 0 ? "▲" : change < 0 ? "▼" : "•"} {Math.abs(change)}%
          </span>
        )}
      </div>
      <div className="presence-figure-label">{label}</div>
    </div>
  );
}

const W = 560;
const H = 120;
const PAD = 6;

function TrendChart({ points }: { points: TrendPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const peak = Math.max(...points.map((p) => p.impressions), 1);

  const xy = points.map((p, i) => ({
    x: PAD + (i / Math.max(points.length - 1, 1)) * (W - PAD * 2),
    y: H - PAD - (p.impressions / peak) * (H - PAD * 2),
    point: p,
  }));

  // A smooth curve reads as a trend; straight segments read as a set of readings.
  const line = xy
    .map((c, i) => {
      if (i === 0) return `M ${c.x.toFixed(1)} ${c.y.toFixed(1)}`;
      const prev = xy[i - 1];
      const midX = (prev.x + c.x) / 2;
      return `C ${midX.toFixed(1)} ${prev.y.toFixed(1)} ${midX.toFixed(1)} ${c.y.toFixed(1)} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`;
    })
    .join(" ");
  const area = `${line} L ${xy[xy.length - 1].x.toFixed(1)} ${H} L ${xy[0].x.toFixed(1)} ${H} Z`;
  const active = hover !== null ? xy[hover] : null;

  return (
    <div className="trend-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="trend-svg" preserveAspectRatio="none">
        <defs>
          <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.32" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#trendFill)" className="trend-area" />
        <path
          d={line}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
          className="trend-line"
        />
        {active && (
          <line x1={active.x} y1={PAD} x2={active.x} y2={H} stroke="var(--text-muted)" strokeWidth="1" vectorEffect="non-scaling-stroke" strokeDasharray="3 3" />
        )}
        {active && <circle cx={active.x} cy={active.y} r="4" fill="var(--accent)" stroke="var(--surface)" strokeWidth="2" />}
        {/* Invisible hit areas: one per day, so hovering anywhere in a column works. */}
        {xy.map((c, i) => (
          <rect
            key={i}
            x={c.x - (W / points.length) / 2}
            y={0}
            width={W / points.length}
            height={H}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          />
        ))}
      </svg>
      <div className="trend-axis">
        {active ? (
          <span className="trend-readout">
            <b>{active.point.impressions.toLocaleString()}</b> impressions
            {active.point.clicks > 0 && <> · <b>{active.point.clicks}</b> clicks</>}
            {active.point.position && <> · #{active.point.position}</>}
            <span className="muted"> · {formatDay(active.point.date)}</span>
          </span>
        ) : (
          <>
            <span>{formatDay(points[0].date)}</span>
            <span className="muted">peak {peak.toLocaleString()}/day</span>
            <span>{formatDay(points[points.length - 1].date)}</span>
          </>
        )}
      </div>
    </div>
  );
}

function TrendEmpty({ reason, siteId }: { reason: SearchPresence["trend_unavailable"]; siteId: number }) {
  const copy: Record<string, { text: string; action?: { href: string; label: string } }> = {
    no_pages: {
      text: "Find your pages first — then Signal can chart how the home page performs in Google.",
      action: { href: `/dashboard/sites/${siteId}`, label: "" },
    },
    no_google: {
      text: "Connect Google Search Console to chart real impressions and clicks for your home page. It's free.",
      action: { href: "/dashboard/settings", label: "Connect Google" },
    },
    no_property: {
      text: "Google is connected, but this site doesn't have a Search Console property picked yet.",
      action: { href: "/dashboard/settings", label: "Pick a property" },
    },
    no_data: {
      text: "No impressions recorded for the home page in the last 28 days. Search Console also lags about two days.",
    },
  };
  const entry = copy[reason ?? "no_data"] ?? copy.no_data;

  return (
    <div className="trend-empty">
      <TrendGhost />
      <p>{entry.text}</p>
      {entry.action?.label && (
        <Link className="btn btn-sm btn-ghost" href={entry.action.href}>
          {entry.action.label}
        </Link>
      )}
    </div>
  );
}

/** A faint, inert line so the empty state still looks like a chart rather than a
 *  hole in the page. Deliberately not animated: it isn't data. */
function TrendGhost() {
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="trend-svg ghost" preserveAspectRatio="none" aria-hidden="true">
      <path
        d="M 6 90 C 80 90 80 60 150 62 C 220 64 220 80 290 70 C 360 60 360 34 430 40 C 500 46 500 28 554 24"
        fill="none"
        stroke="var(--border)"
        strokeWidth="2"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

/** Counts a gauge up to its value once, after `delay`. Skipped entirely when the
 *  reader has asked for reduced motion, or when there's no number to show. */
function useCountUp(target: number, delay: number, enabled: boolean) {
  const [value, setValue] = useState(0);
  const frame = useRef<number>();

  useEffect(() => {
    if (!enabled) return;
    const reduced =
      typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced || target === 0) {
      setValue(target);
      return;
    }
    const DURATION = 900;
    let start: number | null = null;
    const timer = setTimeout(() => {
      const step = (now: number) => {
        start ??= now;
        const t = Math.min((now - start) / DURATION, 1);
        // Ease-out: fast first, settling at the end, so the final number is readable.
        setValue(Math.round(target * (1 - Math.pow(1 - t, 3))));
        if (t < 1) frame.current = requestAnimationFrame(step);
      };
      frame.current = requestAnimationFrame(step);
    }, delay);
    return () => {
      clearTimeout(timer);
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, [target, delay, enabled]);

  return value;
}

function formatDay(iso: string) {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function prettyPath(url: string) {
  try {
    const u = new URL(url);
    return u.pathname === "/" ? u.hostname : `${u.hostname}${u.pathname}`;
  } catch {
    return url;
  }
}
