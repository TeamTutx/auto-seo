// Shared between the page and its server wrapper: the wrapper renders these
// same questions as FAQPage structured data, so an answer edited here can't
// drift from the one Google is shown.
export const FAQ: { q: string; a: string }[] = [
  {
    q: "What is an auto SEO tool?",
    a:
      "Software that performs the repeatable parts of search optimisation on its own: crawling your pages, checking each one against a fixed list of technical and on-page rules, tracking your position for chosen keywords, and ranking what to fix first. The work it automates is measurement and diagnosis — the judgement about what to publish stays yours.",
  },
  {
    q: "Can SEO be fully automated?",
    a:
      "No. Auditing, rank tracking, index checks and drafting a title or meta description can be automated, and Signal automates all of them. Deciding what your site should say, earning links, and publishing changes cannot be — Signal reports and suggests, it does not edit your website for you.",
  },
  {
    q: "Do auto SEO tools build backlinks?",
    a:
      "Signal does not, and treats that as a feature. Automated link building is the part of the category most likely to earn a manual penalty, and a credible backlink product needs a crawled index of the web that costs millions to maintain. Signal covers what happens on your own pages and in search results for them.",
  },
  {
    q: "How is this different from Semrush or Ahrefs?",
    a:
      "Those are data-index businesses — their value is a crawled backlink index and a keyword database with search volumes, sold by subscription from roughly $139 a month. Signal is an audit-and-fix tool with no subscription: you buy credits, they don't expire, and audits, scores and the prioritised action list are free and unlimited.",
  },
  {
    q: "What does an automated SEO audit check?",
    a:
      "Signal runs ten checks on every page — title tag, meta description, heading structure, image alt text, internal and external links, content length, readability, canonical tag, robots meta tag and structured data — plus keyword density once the page has a target keyword. Each page gets a 0–100 score and every failure becomes a line on one ranked list.",
  },
  {
    q: "Is there a free version?",
    a:
      "Signal is free to use. Audits, scores, page discovery, index checks, the opportunities list and your Search Console and Analytics data cost nothing and aren't rate-limited. Credits only pay for the parts that cost real money to run — live rank lookups and AI writing — and new accounts start with free credits, no card required.",
  },
];
