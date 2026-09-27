import type { Metadata } from "next";
import HowItWorksPage from "./how-it-works-page";
import { STEPS } from "./content";
import { SITE_URL } from "@/lib/site";

const TITLE = "How Signal Works, End to End";
const DESCRIPTION =
  "A screenshot walkthrough of Signal: verify a domain, crawl and audit every page, see each fix written as an exact change, apply it to WordPress or GitHub, and undo it.";

// Same split as /auto-seo-tools: the page is a client component because its CTAs
// branch on useAuth, so this wrapper owns metadata and structured data. Steps
// come from ./content so the visible walkthrough and the HowTo markup describe
// the same nine steps.
export const metadata: Metadata = {
  title: `${TITLE} — Signal`,
  description: DESCRIPTION,
  alternates: { canonical: "/how-it-works" },
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: `${SITE_URL}/how-it-works`,
    type: "article",
    images: [{ url: `${SITE_URL}/tour/site-overview.png`, width: 2040, height: 1350 }],
  },
};

const structuredData = [
  {
    "@context": "https://schema.org",
    "@type": "HowTo",
    name: TITLE,
    description: DESCRIPTION,
    totalTime: "PT10M",
    step: STEPS.map((step, i) => ({
      "@type": "HowToStep",
      position: i + 1,
      name: step.title,
      text: step.body,
      url: `${SITE_URL}/how-it-works#${step.id}`,
      image: `${SITE_URL}${step.image.src}`,
    })),
  },
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Signal", item: `${SITE_URL}/` },
      { "@type": "ListItem", position: 2, name: "How it works", item: `${SITE_URL}/how-it-works` },
    ],
  },
];

export default function Page() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }} />
      <HowItWorksPage />
    </>
  );
}
