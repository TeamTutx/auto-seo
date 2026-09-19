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

  const poll = useCallback(async () => {
    try {
      const next = await api.siteJobs(siteId);
      setJobs(next);
      for (const [kind, job] of Object.entries(next) as [JobKind, SiteJobs[JobKind]][]) {
        if (!job || (job.status !== "done" && job.status !== "failed")) continue;
        if (seen.current[kind] === job.id) continue;
        const first = seen.current[kind] === undefined;
        seen.current[kind] = job.id;
        // Don't fire for jobs that already existed when the page opened.
        if (!first) finishRef.current?.(kind);
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
