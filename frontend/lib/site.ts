// Canonical public origin of the marketing site. Used for metadataBase,
// sitemap.xml and robots.txt so they never drift from each other; override with
// NEXT_PUBLIC_SITE_URL for a staging deploy.
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "https://signal-seo.in").replace(/\/+$/, "");
