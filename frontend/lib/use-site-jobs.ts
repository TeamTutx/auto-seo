"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { JobKind, SiteJobs } from "@/lib/types";

const IDLE_MS = 15_000;
const ACTIVE_MS = 2_000;

/** Poll a site's background jobs, fast while something is running and slowly
 *  otherwise. `onFinish` fires once per job that completes, which is what the
 *  pages use to refetch their data the moment a run ends rather than waiting
 *  for the next poll. */
export function useSiteJobs(siteId: number, onFinish?: (kind: JobKind) => void) {
  const [jobs, setJobs] = useState<SiteJobs | null>(null);
  const running = jobs ? Object.values(jobs).some((j) => j && (j.status === "running" || j.status === "queued")) : false;

  // Refs so changing the callback or the last-seen state doesn't restart the
  // interval — that would reset the clock on every render.
  const finishRef = useRef(onFinish);
  finishRef.current = onFinish;
  const seen = useRef<Partial<Record<JobKind, number>>>({});
  // The site whose baseline poll has been taken. That first poll is the
  // baseline — jobs already finished then are the page's starting state, not
  // news; anything that finishes afterwards is. The baseline is per *hook*,
  // not per kind: keyed by kind, a site's very first run of some kind that was
  // already `done` by the poll that discovered it would look pre-existing and
  // never refresh the page. Stubbed or cached jobs finish that fast.
  const baselined = useRef<number | null>(null);

  const poll = useCallback(async () => {
    try {
      const next = await api.siteJobs(siteId);
      setJobs(next);
      // Switching sites starts over: another site's job ids mean nothing here.
      const baseline = baselined.current !== siteId;
      if (baseline) {
        seen.current = {};
        baselined.current = siteId;
      }
      for (const [kind, job] of Object.entries(next) as [JobKind, SiteJobs[JobKind]][]) {
        if (!job || (job.status !== "done" && job.status !== "failed")) continue;
        if (seen.current[kind] === job.id) continue;
        seen.current[kind] = job.id;
        if (!baseline) finishRef.current?.(kind);
      }
    } catch {
      // a failed poll is not worth showing; the next one will tell the story
    }
  }, [siteId]);

  useEffect(() => {
    poll();
    const timer = setInterval(poll, running ? ACTIVE_MS : IDLE_MS);
    return () => clearInterval(timer);
  }, [poll, running]);

  return { jobs, running, refresh: poll };
}
