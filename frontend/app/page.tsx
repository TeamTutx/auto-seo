import type { Metadata } from "next";
import LandingPage from "./landing-page";
import { SITE_URL } from "@/lib/site";

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

export default function Home() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }} />
      <LandingPage />
    </>
  );
}
