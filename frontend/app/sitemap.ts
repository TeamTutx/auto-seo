import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";

// Only the public marketing page belongs here: /login is a thin client-rendered
// form and /dashboard is auth-gated.
export default function sitemap(): MetadataRoute.Sitemap {
  return [{ url: `${SITE_URL}/`, changeFrequency: "weekly", priority: 1 }];
}
