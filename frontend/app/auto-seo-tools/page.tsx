import type { Metadata } from "next";
import AutoSeoToolsPage from "./auto-seo-tools-page";
import { FAQ } from "./content";
import { SITE_URL } from "@/lib/site";

const TITLE = "Auto SEO: What Automated SEO Tools Actually Do";
const DESCRIPTION =
  "What an auto SEO tool automates and what it can't: the 10-point automated on-page checklist, how rank tracking and index checks work, and where automation stops.";

// The page itself is a client component (its CTAs branch on useAuth, same as
// the landing page), so this thin server wrapper owns the metadata and the
// structured data. FAQ answers come from ./content so the visible text and the
// FAQPage markup can't drift apart.
export const metadata: Metadata = {
  title: `${TITLE} — Signal`,
  description: DESCRIPTION,
  alternates: { canonical: "/auto-seo-tools" },
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: `${SITE_URL}/auto-seo-tools`,
    type: "article",
  },
};

const structuredData = [
  {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: TITLE,
    description: DESCRIPTION,
    mainEntityOfPage: { "@type": "WebPage", "@id": `${SITE_URL}/auto-seo-tools` },
    author: { "@type": "Organization", name: "Signal", url: `${SITE_URL}/` },
    publisher: { "@type": "Organization", name: "Signal", url: `${SITE_URL}/` },
    about: "Automated SEO tools",
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: FAQ.map((item) => ({
      "@type": "Question",
      name: item.q,
      acceptedAnswer: { "@type": "Answer", text: item.a },
    })),
  },
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Signal", item: `${SITE_URL}/` },
      { "@type": "ListItem", position: 2, name: "Auto SEO tools", item: `${SITE_URL}/auto-seo-tools` },
    ],
  },
];

export default function Page() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }} />
      <AutoSeoToolsPage />
    </>
  );
}
