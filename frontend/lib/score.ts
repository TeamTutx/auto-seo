export type ScoreBucket = "good" | "warn" | "bad";

export function scoreBucket(score: number | null | undefined): ScoreBucket {
  if (score === null || score === undefined) return "bad";
  if (score >= 80) return "good";
  if (score >= 50) return "warn";
  return "bad";
}

export function scoreColorVar(score: number | null | undefined): string {
  const bucket = scoreBucket(score);
  return bucket === "good" ? "var(--good)" : bucket === "warn" ? "var(--warn)" : "var(--bad)";
}
