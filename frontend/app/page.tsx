import type { Metadata } from "next";
import LandingPage from "./landing-page";
import { DEFAULT_PRICING } from "@/lib/default-pricing";
import { API_URL, SITE_URL } from "@/lib/site";
import type { Pricing } from "@/lib/types";

// Prices are edited in /admin/pricing and read from the API. Fetched on the
// server so the HTML crawlers (and Dodo's reviewers) see carries the real
// prices, and re-fetched at most every 5 minutes so an edit shows up without a
// redeploy. If the API is down we fall back to the seeded defaults.
export const revalidate = 300;

async function getPricing(): Promise<Pricing> {
  try {
    const res = await fetch(`${API_URL}/pricing`, { next: { revalidate: 300 }, signal: AbortSignal.timeout(8000) });
    if (res.ok) return (await res.json()) as Pricing;
  } catch {
    // API unreachable (e.g. Render cold start during a build) - use the fallback
  }
  return DEFAULT_PRICING;
}

// The landing page itself is a client component (it reads useAuth() to swap its
// CTAs), and client components can't export metadata - so this thin server
// wrapper owns the page's canonical URL and structured data. Title/description
// come from the root layout. Edit the visible page in ./landing-page.tsx.
export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

const structuredData = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "Signal",
  url: `${SITE_URL}/`,
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web",
  description:
    "Self-serve SEO platform: on-page audits, keyword rank tracking with competitor comparison, AI-assisted fixes, and Google Search Console and Analytics data.",
};

export default async function Home() {
  const pricing = await getPricing();
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }} />
      <LandingPage pricing={pricing} />
    </>
  );
}
