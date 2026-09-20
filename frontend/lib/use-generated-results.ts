"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { GeneratedResult } from "@/lib/types";

/** Everything a credit has already bought for this page, so a reload restores
 *  it instead of asking the user to pay for the same answer again. Keyed
 *  `kind` for page-scoped results and `kind::subject` for keyword-scoped ones.
 *  Returns null until loaded, so a component can tell "nothing yet" apart from
 *  "not fetched". */
export function useGeneratedResults(pageId: number) {
  const [results, setResults] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    let cancelled = false;
    setResults(null);
    api
      .pageGeneratedResults(pageId)
      .then((rows: GeneratedResult[]) => {
        if (cancelled) return;
        setResults(
          Object.fromEntries(rows.map((r) => [r.subject ? `${r.kind}::${r.subject}` : r.kind, r.payload]))
        );
      })
      // Nothing restored is a worse page, not a broken one - the buttons still work.
      .catch(() => !cancelled && setResults({}));
    return () => {
      cancelled = true;
    };
  }, [pageId]);

  return results;
}
