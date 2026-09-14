import type { ScoreTrendPoint } from "@/lib/types";

const WIDTH = 640;
const HEIGHT = 90;
const PADDING = 8;

// Higher score = better, so unlike RankHistoryChart the y-axis is NOT inverted.
export default function ScoreTrendChart({ trend }: { trend: ScoreTrendPoint[] }) {
  if (trend.length === 0) {
    return <div style={{ color: "var(--text-muted)", fontSize: 12.5 }}>No audit history yet to chart.</div>;
  }
  if (trend.length === 1) {
    return (
      <div style={{ color: "var(--text-muted)", fontSize: 12.5 }}>
        Only one data point so far ({trend[0].score}) — rescan later to see a trend.
      </div>
    );
  }

  const scores = trend.map((p) => p.score);
  const minScore = Math.min(...scores);
  const maxScore = Math.max(...scores);
  const span = Math.max(maxScore - minScore, 1);

  const coords = trend.map((p, i) => {
    const x = PADDING + (i / (trend.length - 1)) * (WIDTH - PADDING * 2);
    const y = PADDING + ((maxScore - p.score) / span) * (HEIGHT - PADDING * 2);
    return { x, y };
  });

  const path = coords.map((c, i) => `${i === 0 ? "M" : "L"} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(" ");

  return (
    <div>
      <svg width="100%" height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="none">
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        {coords.map((c, i) => (
          <circle key={i} cx={c.x} cy={c.y} r="2.5" fill="var(--accent)" />
        ))}
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)" }}>
        <span>lowest {minScore}</span>
        <span>peak {maxScore}</span>
      </div>
    </div>
  );
}
