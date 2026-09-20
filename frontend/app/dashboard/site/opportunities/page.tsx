"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { routes, useRouteId } from "@/lib/routes";
import OpportunitiesPanel from "@/components/OpportunitiesPanel";
import type { Site } from "@/lib/types";

/** The ranked list of what's wrong and what to do about it, on its own page.
 *  It used to sit on the site overview; that slot now belongs to the visibility
 *  gauges. The list itself stays — marking a fix as applied, so the next scan
 *  can confirm it worked, only exists here. */
function OpportunitiesPage() {
  const siteId = useRouteId("id");
  const [site, setSite] = useState<Site | null>(null);

  useEffect(() => {
    api.getSite(siteId).then(setSite).catch(() => {});
  }, [siteId]);

  return (
    <div>
      <div className="topbar">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="breadcrumb">
            <Link href={routes.site(siteId)} className="link-btn">
              {site?.domain ?? "Site"}
            </Link>{" "}
            / Fixes
          </div>
          <h1 className="page-title">What to fix</h1>
          <div className="page-sub">
            Ranked by impact. Apply a fix, mark it done, and the next scan confirms whether it worked.
          </div>
        </div>
      </div>

      <OpportunitiesPanel siteId={siteId} />
    </div>
  );
}

// useSearchParams has to sit inside a Suspense boundary or `next build` fails
// (see CLAUDE.md). Same shape as /login, which has always read its query string.
export default function Page() {
  return (
    <Suspense fallback={<div className="loading-state">Loading…</div>}>
      <OpportunitiesPage />
    </Suspense>
  );
}
