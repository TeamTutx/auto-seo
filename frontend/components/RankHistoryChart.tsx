import type { KeywordRank } from "@/lib/types";

const WIDTH = 220;
const HEIGHT = 60;
const PADDING = 6;

// Lower rank number = better, so the y-axis is inverted (best rank at top).
export default function RankHistoryChart({ history }: { history: KeywordRank[] }) {
  const points = history.filter((h) => h.rank_position !== null) as (KeywordRank & { rank_position: number })[];

  if (points.length === 0) {
    return <div style={{ color: "var(--text-muted)", fontSize: 12 }}>No successful checks yet to chart.</div>;
  }
  if (points.length === 1) {
    return (
      <div style={{ color: "var(--text-muted)", fontSize: 12 }}>
        Only one data point so far (#{points[0].rank_position}) — check again later to see a trend.
      </div>
    );
  }

  const ranks = points.map((p) => p.rank_position);
  const minRank = Math.min(...ranks);
  const maxRank = Math.max(...ranks);
  const span = Math.max(maxRank - minRank, 1);

  const coords = points.map((p, i) => {
    const x = PADDING + (i / (points.length - 1)) * (WIDTH - PADDING * 2);
    const y = PADDING + ((p.rank_position - minRank) / span) * (HEIGHT - PADDING * 2);
    return { x, y, rank: p.rank_position, date: p.checked_at };
  });

  const path = coords.map((c, i) => `${i === 0 ? "M" : "L"} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(" ");

  return (
    <div>
      <svg width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`}>
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
        {coords.map((c, i) => (
          <circle key={i} cx={c.x} cy={c.y} r="2.5" fill="var(--accent)" />
        ))}
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)" }}>
        <span>best #{minRank}</span>
        <span>worst #{maxRank}</span>
      </div>
    </div>
  );
}
