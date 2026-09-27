/** What Signal did to this page.
 *
 *  Everything here is checkable by the reader, which is the entire point of the
 *  section: the pull requests are public on the repository, and the title and
 *  description below are what `view-source:https://signal-seo.in` returns right
 *  now. It exists instead of testimonials because Signal has three accounts and
 *  no one to quote, and invented quotes are the first thing a sceptical buyer
 *  checks.
 *
 *  **Re-verify before editing.** The audit score and the two values move when
 *  the page changes:
 *    curl -s https://signal-seo.in/ | grep -E '<title>|name="description"'
 */
export interface ProofChange {
  field: string;
  before: string;
  after: string;
  /** The pull request Signal opened for it. */
  pr: { number: number; url: string };
}

export const REPO_URL = "https://github.com/TeamTutx/auto-seo";

export const PROOF_CHANGES: ProofChange[] = [
  {
    field: "Meta description",
    before:
      "Run on-page SEO audits, track keyword rankings against your competitors, and get AI-written fixes, with real Google Search Console data.",
    after:
      "Discover how Signal's auto SEO tools streamline your SEO audits, rank tracking, and AI fixes, helping you improve your website's performance effortlessly.",
    pr: { number: 1, url: `${REPO_URL}/pull/1` },
  },
  {
    field: "Title tag",
    before: "Signal — SEO audits, rank tracking and AI fixes",
    after: "SEO Audit Tool | Track Rankings & AI Fixes with Signal",
    pr: { number: 2, url: `${REPO_URL}/pull/2` },
  },
];

/** Verified 2026-09-28 against the live page. */
export const PROOF_SCORE = { now: 91, checksPassing: "both", total: 11 };
