"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { legacyPathToRoute } from "@/lib/routes";

/** Where the old path-style dashboard URLs land.
 *
 *  render.yaml *rewrites* (not redirects) `/dashboard/sites/*` and
 *  `/admin/users/*` here, which means the browser's address bar still holds the
 *  original path — so this page can read it and send the visitor to the query
 *  string equivalent. A Render redirect rule can't do it alone: the destination
 *  would need the captured id inside a query string, which isn't a documented
 *  substitution. Doing it here is one small page and is exactly testable.
 *
 *  It runs for bookmarks and pasted links only; everything inside the app links
 *  through `routes`, so nothing reaches this page in normal use. */
export default function LegacyLinkPage() {
  const router = useRouter();

  useEffect(() => {
    const target = legacyPathToRoute(window.location.pathname);
    router.replace(target ?? "/dashboard");
  }, [router]);

  return <div className="loading-state">Taking you there…</div>;
}
