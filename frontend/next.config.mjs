/** @type {import('next').NextConfig} */
const nextConfig = {
  // Built as a static export and served from Render's CDN as plain files.
  // Consequences worth knowing before adding a page: no server at request time,
  // so no route handlers, no ISR, and no dynamic route segments unless they can
  // be enumerated at build time (they can't be, for per-user ids - that's why
  // the dashboard passes ids in the query string; see lib/routes.ts).
  output: "export",
};

export default nextConfig;
