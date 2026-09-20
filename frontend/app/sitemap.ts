import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";

// Only public content belongs here: the marketing pages and the legal pages.
// /login is a thin client-rendered form; /dashboard and /admin are auth-gated.
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${SITE_URL}/`, changeFrequency: "weekly", priority: 1 },
    { url: `${SITE_URL}/auto-seo-tools`, changeFrequency: "monthly", priority: 0.8 },
    { url: `${SITE_URL}/terms`, changeFrequency: "yearly", priority: 0.3 },
    { url: `${SITE_URL}/privacy`, changeFrequency: "yearly", priority: 0.3 },
    { url: `${SITE_URL}/refunds`, changeFrequency: "yearly", priority: 0.3 },
  ];
}
