import { scoreColorVar } from "@/lib/score";

const RADIUS = 62;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export default function ScoreGauge({ score }: { score: number | null }) {
  const pct = score ?? 0;
  const offset = CIRCUMFERENCE * (1 - pct / 100);
  const color = score === null ? "var(--text-muted)" : scoreColorVar(score);

  return (
    <div className="gauge-wrap">
      <svg width="150" height="150" viewBox="0 0 150 150">
        <circle cx="75" cy="75" r={RADIUS} fill="none" stroke="var(--border)" strokeWidth="10" />
        {score !== null && (
          <circle
            cx="75"
            cy="75"
            r={RADIUS}
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={offset}
            strokeLinecap="round"
            transform="rotate(-90 75 75)"
          />
        )}
      </svg>
      <div className="gauge-value">
        {score === null ? "—" : score}
        <span>/100</span>
      </div>
    </div>
  );
}
