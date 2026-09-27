/** The tour's steps, shared so the visible page and its HowTo structured data
 *  describe the same thing. Every screenshot is Signal's real interface, captured
 *  by tools/tour/capture.mjs against a demo account - re-run that when the UI
 *  moves, or this page quietly starts lying. */
export interface Step {
  id: string;
  n: number;
  title: string;
  body: string;
  /** Extra detail worth knowing, shown smaller. */
  note?: string;
  image: { src: string; alt: string; width: number; height: number };
  /** Rendered narrow: a cropped card rather than a whole screen. */
  narrow?: boolean;
}

export const STEPS: Step[] = [
  {
    id: "verify",
    n: 1,
    title: "Add your domain and prove it is yours",
    body:
      "You give Signal a domain, not a list of URLs. Ownership is proved the same three ways Search Console offers — a DNS TXT record, a meta tag, or a file at your site's root.",
    note:
      "This is also what unlocks writing to your site later. Signal will not touch a domain nobody has proved they own.",
    image: {
      src: "/tour/connect.png",
      alt: "The Applying fixes panel showing a connected WordPress site and what Signal can write to it.",
      width: 1548,
      height: 228,
    },
    narrow: true,
  },
  {
    id: "scan",
    n: 2,
    title: "Signal finds your pages and scores them",
    body:
      "It crawls from your sitemap and your own links, audits every page it finds, and rolls the results into one score. Nothing here costs a credit — crawling, auditing and scoring are free and unlimited.",
    note:
      "Search presence sits on the same screen: how many of your tracked keywords rank in Google, and how many are named in AI answers.",
    image: {
      src: "/tour/site-overview.png",
      alt: "A site overview showing an SEO score of 50 out of 100, pages tracked, index status and search presence gauges.",
      width: 2040,
      height: 1350,
    },
  },
  {
    id: "audit",
    n: 3,
    title: "Every check, and what is actually wrong",
    body:
      "Eleven checks per page — title, meta description, headings, alt text, links, content length, keyword density, readability, canonical, robots and structured data. Each one says what it found, not just whether it passed.",
    image: {
      src: "/tour/page-audit.png",
      alt: "A page audit listing each check with its status and a plain-English explanation of the problem.",
      width: 2040,
      height: 1350,
    },
  },
  {
    id: "fix",
    n: 4,
    title: "The fix, written as an exact change",
    body:
      "Signal writes the replacement and shows it against what is on the page now. Not advice about what a good meta description would contain — the text, next to the thing it replaces.",
    note:
      "One credit, because a model wrote it. A canonical or robots tag costs nothing: those are computed, not generated.",
    image: {
      src: "/tour/fix-diff.png",
      alt: "A meta description fix showing nothing on the page now and the new description that would replace it.",
      width: 767,
      height: 434,
    },
    narrow: true,
  },
  {
    id: "apply",
    n: 5,
    title: "Signal makes the change, and you can undo it",
    body:
      "Connect WordPress or a GitHub repository and Signal sets the value itself. On WordPress it is live when the button finishes. On GitHub it is a pull request you review and merge — never a push to your default branch.",
    note:
      "Applying is free, and so is undoing it. The credit paid for writing the fix; a button you hesitate over is a button you do not press.",
    image: {
      src: "/tour/fix-applied.png",
      alt: "Alt text applied to two images, showing what each was before, and an Undo button.",
      width: 767,
      height: 642,
    },
    narrow: true,
  },
  {
    id: "keywords",
    n: 6,
    title: "Decide what you are trying to rank for",
    body:
      "Signal suggests keywords from your Search Console data, your own page content and Google's related searches, and labels where each came from. You pick the ones worth tracking.",
    note:
      "Only the Search Console ideas carry real numbers, because those are searches you have actually appeared for. Signal has no volume database and will not invent one.",
    image: {
      src: "/tour/keywords.png",
      alt: "Keyword ideas with their source and, for Search Console ideas, real impressions and clicks.",
      width: 2040,
      height: 1350,
    },
  },
  {
    id: "visibility",
    n: 7,
    title: "Check Google, AI Overviews and ChatGPT",
    body:
      "Ranking is no longer the whole question. For each keyword Signal checks where you rank, whether Google's AI Overview cites you, and whether an assistant names you when asked — and captures who won instead.",
    note:
      "That evidence is what the advice is built from. A plan written without it is generic SEO advice, which helps nobody.",
    image: {
      src: "/tour/visibility.png",
      alt: "A visibility report showing Google position, AI Overview citation and ChatGPT mention for a keyword.",
      width: 2040,
      height: 1350,
    },
  },
  {
    id: "opportunities",
    n: 8,
    title: "Everything that needs doing, in one ranked list",
    body:
      "Failing checks and struggling keywords across every page, ordered by severity. The fix for anything Signal can apply is right there in the list, so you never go hunting for the page it belongs to.",
    image: {
      src: "/tour/opportunities.png",
      alt: "A prioritised opportunities list combining audit failures and keyword problems across a site.",
      width: 2040,
      height: 1350,
    },
  },
  {
    id: "credits",
    n: 9,
    title: "You pay for results, not for looking at them",
    body:
      "Signal sells credits and nothing else — no tiers, nothing recurring. A credit is spent when something costs Signal real money: a rank lookup, or a model writing something for you.",
    note:
      "Re-opening anything a credit already bought is free. So are audits, scores, crawling, index checks and your Search Console data.",
    image: {
      src: "/tour/billing.png",
      alt: "The billing page listing what each action costs in credits and what is free.",
      width: 2040,
      height: 1350,
    },
  },
];

/** The part that keeps the rest credible. */
export const LIMITS: { title: string; body: string }[] = [
  {
    title: "It stops at your copy",
    body:
      "Signal sets titles, meta descriptions, alt text, canonical and robots tags and structured data — things with one correct value. It drafts heading outlines and rewrites, and you apply those, because a wrong tag is a wrong tag while a rewritten paragraph is a page that no longer says what you meant.",
  },
  {
    title: "No link building",
    body:
      "No backlink index, no outreach. Automated link building is the fastest route to a manual action, and doing it properly means maintaining a crawl of the web — a different business at a different price.",
  },
  {
    title: "No invented numbers",
    body:
      "No search volumes, no difficulty scores, no traffic estimates. Where Signal has real data it shows it and says where it came from; where it does not, it says so instead of guessing.",
  },
  {
    title: "It will not decide what to publish",
    body:
      "Signal can tell you the pages beating you all answer the question in their first paragraph. Whether that is a question your business should answer is not a machine's call.",
  },
];
