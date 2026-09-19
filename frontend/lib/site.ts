// Canonical public origin of the marketing site. Used for metadataBase,
// sitemap.xml and robots.txt so they never drift from each other; override with
// NEXT_PUBLIC_SITE_URL for a staging deploy.
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "https://signal-seo.in").replace(/\/+$/, "");

// Where customers reach a human - shown on the legal pages and in the footer
// (Dodo Payments requires a monitored contact route before approving a
// merchant). Override with NEXT_PUBLIC_SUPPORT_EMAIL.
export const SUPPORT_EMAIL = process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "gharshit1237@gmail.com";

// The API origin, for server-side fetches (the browser client has its own copy
// in lib/api.ts).
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
