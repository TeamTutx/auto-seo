"use client";

import type { SiteJob } from "@/lib/types";

/** The banner under a "start this" button while a background run is in flight,
 *  and the result once it isn't. Deliberately shows credits spent: these runs
 *  cost real money and a number appearing without explanation is how billing
 *  surprises happen. */
export default function JobProgress({ job, idleHint }: { job: SiteJob | null; idleHint?: string }) {
  if (!job) return idleHint ? <div className="job-banner idle">{idleHint}</div> : null;

  if (job.status === "failed") {
    return (
      <div className="job-banner failed">
        <b>That didn’t finish.</b> {job.error ?? "Something went wrong."}
      </div>
    );
  }

  const active = job.status === "running" || job.status === "queued";
  const pct = job.total > 0 ? Math.min(100, Math.round((job.progress / job.total) * 100)) : active ? 0 : 100;

  return (
    <div className={`job-banner ${active ? "active" : "done"}`}>
      <div className="job-banner-row">
        <span>{job.message ?? (active ? "Starting…" : "Finished.")}</span>
        {job.credits_spent > 0 && (
          <span className="job-credits">
            {job.credits_spent} credit{job.credits_spent === 1 ? "" : "s"}
          </span>
        )}
      </div>
      {active && (
        <div className="job-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="job-bar-fill" style={{ width: `${pct || 6}%` }} />
        </div>
      )}
    </div>
  );
}
