import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    // /dashboard and /admin are the auth-gated product (a loading shell for anyone
    // signed out) - nothing there is worth crawling.
    rules: [{ userAgent: "*", allow: "/", disallow: ["/dashboard", "/admin"] }],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
