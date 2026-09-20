"use client";

import { useSearchParams } from "next/navigation";

/** Every dashboard URL that carries an id, built in one place.
 *
 *  These used to be path segments (`/dashboard/sites/7/visibility`). The site is
 *  a static export now - Render serves it as files off a CDN, with no server to
 *  render a route per site - and a static export can only pre-render dynamic
 *  segments it can enumerate at build time, which per-user ids are not. Query
 *  strings need no such enumeration: one exported page serves every id.
 *
 *  Old links still work: the `routes` rules in render.yaml rewrite
 *  `/dashboard/sites/*` and `/admin/users/*` to /legacy-link, which translates
 *  them client-side. See `legacyPathToRoute` below. */
export const routes = {
  site: (siteId: number | string) => `/dashboard/site?id=${siteId}`,
  siteKeywords: (siteId: number | string) => `/dashboard/site/keywords?id=${siteId}`,
  siteVisibility: (siteId: number | string) => `/dashboard/site/visibility?id=${siteId}`,
  siteOpportunities: (siteId: number | string) => `/dashboard/site/opportunities?id=${siteId}`,
  page: (siteId: number | string, pageId: number | string) =>
    `/dashboard/page?site=${siteId}&id=${pageId}`,
  adminUser: (userId: number | string) => `/admin/user?id=${userId}`,
};

/** Translate one of the old path-style URLs to its query-string equivalent, or
 *  null if it isn't one. Exported (and tested) separately from the page that
 *  uses it so the mapping can be checked without a browser. */
export function legacyPathToRoute(pathname: string): string | null {
  const parts = pathname.replace(/^\/+|\/+$/g, "").split("/");

  // /admin/users/:id
  if (parts[0] === "admin" && parts[1] === "users" && parts[2]) {
    return routes.adminUser(parts[2]);
  }
  // /dashboard/sites/:siteId[/keywords|/visibility|/opportunities|/pages/:pageId]
  if (parts[0] === "dashboard" && parts[1] === "sites" && parts[2]) {
    const siteId = parts[2];
    switch (parts[3]) {
      case undefined:
        return routes.site(siteId);
      case "keywords":
        return routes.siteKeywords(siteId);
      case "visibility":
        return routes.siteVisibility(siteId);
      case "opportunities":
        return routes.siteOpportunities(siteId);
      case "pages":
        return parts[4] ? routes.page(siteId, parts[4]) : routes.site(siteId);
      default:
        return routes.site(siteId);
    }
  }
  return null;
}

/** The `id` (or another named param) from the query string, as a number.
 *  Returns NaN when it's missing or not a number, which every caller already
 *  has to handle - the id used to come from the path and could be junk there
 *  too. Callers must sit inside a <Suspense> boundary; see the note in
 *  CLAUDE.md about `useSearchParams` and `next build`. */
export function useRouteId(param = "id"): number {
  return Number(useSearchParams().get(param));
}
