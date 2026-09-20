"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { SUPPORT_EMAIL } from "@/lib/site";
import { FAQ } from "./content";

// Every claim on this page has to be something Signal actually does today -
// same rule as the landing page (see CLAUDE.md "Landing page parity"). The
// "what it can't do" section is load-bearing, not modesty: link building and
// search volumes are the two things visitors arrive expecting, and saying so
// plainly is what keeps the rest of the page trustworthy.

/** The real on-page audit, in the order backend/app/services/audit_engine.py
 *  runs it. Ten checks on every page, plus keyword density once a page has a
 *  target keyword - keep this in step with `run_onpage_audit`. */
const CHECKLIST: { name: string; what: string }[] = [
  {
    name: "Title tag",
    what: "Present, one of them, a sensible length, and not a duplicate of another page on the same site.",
  },
  {
    name: "Meta description",
    what: "Present and within the length Google will actually render instead of rewriting.",
  },
  {
    name: "Heading structure",
    what: "Exactly one H1, and levels that descend in order — no H2 jumping straight to an H4.",
  },
  {
    name: "Image alt text",
    what: "Every image carries a description, so the page is readable without the pictures.",
  },
  {
    name: "Internal and external links",
    what: "How many of each the page has. A page nothing links to is a page search engines reach last.",
  },
  {
    name: "Content length",
    what: "Word count, so a thin page that can't answer the query is visible as thin.",
  },
  {
    name: "Readability",
    what: "Flesch Reading Ease over the page's own text, with the sentences that dragged the score down.",
  },
  {
    name: "Canonical tag",
    what: "Present and pointing somewhere, so duplicates don't compete with each other.",
  },
  {
    name: "Robots meta tag",
    what: "Nothing on the page is quietly telling search engines not to index it.",
  },
  {
    name: "Structured data",
    what: "Whether schema.org markup is on the page at all — the machine-readable version of what it's about.",
  },
];

const FEATURES: { title: string; body: string; tag: string }[] = [
  {
    tag: "Automated",
    title: "Keyword rank tracking",
    body:
      "Track a keyword per page with a location and device, and re-check every tracked keyword on a page in one click. Each check records a position, so rank history builds itself — and the same lookup shows which pages hold the spots above you.",
  },
  {
    tag: "Automated",
    title: "Technical and on-page fixes",
    body:
      "The audit finds the problem; Signal writes the fix. Six kinds — title, meta description, heading outline, a simpler rewrite, internal link suggestions and image alt text — each generated from that page's real content, not a template. You paste it in, mark it applied, and the next scan confirms the check cleared.",
  },
  {
    tag: "Automated",
    title: "Page discovery and index checks",
    body:
      "Give Signal a domain and it reads the sitemap, or follows your own links when there isn't one, then asks which of those pages Google has actually indexed. A page that isn't indexed can't rank, whatever its audit score says.",
  },
  {
    tag: "Automated",
    title: "Visibility in AI answers",
    body:
      "For every keyword you target, Signal checks where you rank in Google, whether its AI Overview cites you — and who it cited instead — and whether an AI assistant names you when asked that question directly.",
  },
  {
    tag: "Free",
    title: "Your real Search Console and Analytics data",
    body:
      "Connect Google once and each page shows the impressions, clicks and queries it actually earned, next to its audit. Measured numbers, not estimates, and they cost no credits.",
  },
];


export default function AutoSeoToolsPage() {
  const { user } = useAuth();

  const primaryHref = user ? "/dashboard" : "/login?mode=register";
  const primaryLabel = user ? "Go to dashboard" : "Get started free";

  return (
    <div className="lp-page">
      <nav className="lp-nav">
        <div className="lp-nav-inner">
          <Link href="/" className="brand">
            <span className="brand-mark" />
            <span className="brand-name">Signal</span>
          </Link>
          <div className="lp-nav-links">
            <Link href="/#features">Features</Link>
            <Link href="/#how">How it works</Link>
            <Link href="/#plans">Pricing</Link>
          </div>
          <div className="lp-nav-actions">
            {user ? (
              <Link className="btn" href="/dashboard">
                Go to dashboard
              </Link>
            ) : (
              <>
                <Link className="btn btn-ghost" href="/login">
                  Log in
                </Link>
                <Link className="btn" href="/login?mode=register">
                  Get started free
                </Link>
              </>
            )}
          </div>
        </div>
      </nav>

      <article className="lp-section lp-doc">
        <div className="lp-doc-head">
          <div className="lp-kicker">Auto SEO</div>
          <h1>What automated SEO tools actually do</h1>
          <p className="lp-doc-lead">
            An auto SEO tool does the repeatable parts of search optimisation for you: it finds your pages, checks
            every one against a fixed list of technical and on-page rules, tracks where you rank for the keywords
            you care about, and puts what to fix first at the top of one list. What it can&apos;t do is decide what
            your site should say or earn links for you — and the honest version of this category is worth more to
            you than the version that claims otherwise.
          </p>
          <p className="lp-doc-lead-note">
            This page explains how these tools work, what the automation is genuinely good at, where it stops, and
            exactly what Signal automates today.
          </p>
        </div>

        <section className="lp-doc-section" id="what">
          <h2>What &ldquo;auto SEO&rdquo; means in practice</h2>
          <p>
            Three things in search optimisation repeat often enough to be worth handing to software, and they are
            the three that every credible auto SEO tool is built around.
          </p>
          <ul className="lp-doc-list">
            <li>
              <b>Measurement.</b> Which of your pages exist, which Google has indexed, where each one ranks, what
              people searched to find it. All of it is a lookup, and all of it goes stale — which is exactly the
              kind of work a person should not be doing by hand.
            </li>
            <li>
              <b>Diagnosis.</b> Checking a page against rules that don&apos;t change from site to site: one H1,
              a canonical tag, alt text on images, a title that isn&apos;t a duplicate. A machine applies the same
              list to page 200 as carefully as to page 1.
            </li>
            <li>
              <b>Verification.</b> Confirming a fix actually landed. This is the step most tools skip, and the one
              that turns a list of problems into a list of resolved problems.
            </li>
          </ul>
          <p>
            Everything else sold under the label — automatic link building, spun content, &ldquo;set and
            forget&rdquo; rankings — is either someone else&apos;s index being resold or a good way to collect a
            manual penalty.
          </p>
        </section>

        <section className="lp-doc-section" id="how">
          <h2>How an auto SEO tool works</h2>
          <p>Four stages, in this order. Signal runs all four; most tools stop after the second.</p>
          <div className="lp-steps-grid lp-doc-steps">
            <div className="lp-step">
              <div className="lp-step-num">1</div>
              <h4>Find the pages</h4>
              <p>
                Read the sitemap, or follow the site&apos;s own links when there isn&apos;t one, and build the list
                of pages that actually exist — then check which of them Google has indexed.
              </p>
            </div>
            <div className="lp-step">
              <div className="lp-step-num">2</div>
              <h4>Audit each one</h4>
              <p>
                Run the same fixed checklist against every page, score it out of 100, and say in plain words what
                failed and what the fix is.
              </p>
            </div>
            <div className="lp-step">
              <div className="lp-step-num">3</div>
              <h4>Measure what search does with it</h4>
              <p>
                Look up the position for each tracked keyword, who holds the spots above it, whether Google&apos;s
                AI answer cites the page, and what Search Console recorded for it.
              </p>
            </div>
            <div className="lp-step">
              <div className="lp-step-num">4</div>
              <h4>Fix, then verify</h4>
              <p>
                Generate the replacement text, apply it yourself, and let the next scan confirm the check cleared —
                so the list shrinks for a reason.
              </p>
            </div>
          </div>
        </section>

        <section className="lp-doc-section" id="checklist">
          <h2>The automated on-page SEO checklist</h2>
          <p>
            This is the list Signal runs against every page, in order, on every audit. It&apos;s worth reading even
            if you never use the tool — a person can work through it by hand on one page in about ten minutes,
            which is precisely why nobody does it on two hundred.
          </p>
          <ol className="lp-checklist">
            {CHECKLIST.map((item) => (
              <li key={item.name}>
                <b>{item.name}</b>
                <span>{item.what}</span>
              </li>
            ))}
          </ol>
          <p className="lp-doc-note">
            An eleventh check, keyword density, runs once a page has a target keyword set — it compares how often
            that phrase appears against the page&apos;s total word count. Every check returns pass, warning or fail
            with the reason, the page&apos;s score is calculated from them, and each failure becomes one line on a
            site-wide list ranked by severity.
          </p>
        </section>

        <section className="lp-doc-section" id="automates">
          <h2>What Signal automates</h2>
          <p>
            Signal is an auto SEO tool for your own pages: audits, rankings and AI-assisted fixes in one app, with
            no subscription. Here is the whole of it.
          </p>
          <div className="lp-doc-features">
            {FEATURES.map((feature) => (
              <div className="lp-doc-feature" key={feature.title}>
                <div className="lp-doc-feature-tag">{feature.tag}</div>
                <h3>{feature.title}</h3>
                <p>{feature.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="lp-doc-section" id="limits">
          <h2>What auto SEO tools can&apos;t automate</h2>
          <p>
            The useful question about any tool in this category is where it stops. Signal&apos;s answer, without
            hedging:
          </p>
          <ul className="lp-doc-list lp-doc-list-cross">
            <li>
              <b>Link building.</b> Signal has no backlink index and does no outreach. Automated link building is
              the fastest route to a manual action, and doing it properly means maintaining a crawl of the web —
              a business with a different shape and a different price.
            </li>
            <li>
              <b>Search volumes and difficulty scores.</b> Signal suggests keyword ideas from your Search Console,
              your page content and Google&apos;s related searches, and labels where each came from. Only the
              Search Console ones carry real numbers, because those are searches you have actually appeared for.
              Signal has no volume database and won&apos;t invent one.
            </li>
            <li>
              <b>Changing your website.</b> Signal writes the replacement title, the meta description, the heading
              outline — you paste them in. Nothing connects to your CMS and nothing edits your pages.
            </li>
            <li>
              <b>Deciding what to publish.</b> A tool can tell you the pages beating you all answer the question in
              their first paragraph. Whether that question is one your business should be answering is not a
              machine&apos;s call.
            </li>
          </ul>
        </section>

        <section className="lp-doc-section" id="vs">
          <h2>Auto SEO tools vs. the big SEO suites</h2>
          <p>
            Semrush, Ahrefs and their peers are data-index businesses: their value is a crawled backlink index and
            a keyword database with search volumes, rented monthly. An auto SEO tool like Signal is a different
            trade — it goes deep on your own pages and what search does with them, and skips the index entirely.
          </p>
          <div className="lp-doc-table-wrap">
            <table className="lp-doc-table">
              <thead>
                <tr>
                  <th>&nbsp;</th>
                  <th>Signal</th>
                  <th>A full SEO suite</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>On-page audit</td>
                  <td>10 checks per page, 0–100 score, unlimited</td>
                  <td>Yes, plus JS rendering and crawl-depth analysis</td>
                </tr>
                <tr>
                  <td>Rank tracking</td>
                  <td>Per page, location and device, on demand</td>
                  <td>Hundreds to thousands of keywords, daily</td>
                </tr>
                <tr>
                  <td>Fix written for you</td>
                  <td>Six kinds, from the page&apos;s own content</td>
                  <td>Content optimisation, article generation</td>
                </tr>
                <tr>
                  <td>Fix → verify loop</td>
                  <td>Mark applied, next scan confirms it cleared</td>
                  <td>Rare</td>
                </tr>
                <tr>
                  <td>AI answer visibility</td>
                  <td>Google AI Overview and an AI assistant</td>
                  <td>Usually more engines, at a higher tier</td>
                </tr>
                <tr>
                  <td>Backlink index</td>
                  <td>None</td>
                  <td>Core product</td>
                </tr>
                <tr>
                  <td>Search volumes</td>
                  <td>None — labelled ideas instead</td>
                  <td>Core product</td>
                </tr>
                <tr>
                  <td>Pricing</td>
                  <td>Free to use, credits for the metered parts, no subscription</td>
                  <td>From roughly $139/month</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="lp-doc-note">
            Suite pricing checked 20 September 2026; these companies restructure often, so treat it as the order of
            magnitude rather than a quote. If you need a backlink index or search volumes, buy one of those — they
            are genuinely good at it, and Signal is not competing for that job.
          </p>
        </section>

        <section className="lp-doc-section" id="faq">
          <h2>Common questions</h2>
          <div className="lp-doc-faq">
            {FAQ.map((item) => (
              <div className="lp-doc-faq-item" key={item.q}>
                <h3>{item.q}</h3>
                <p>{item.a}</p>
              </div>
            ))}
          </div>
        </section>
      </article>

      <div className="lp-section lp-cta-band">
        <h2>Run the checklist against your own pages.</h2>
        <p>
          Add a site, verify it, and Signal has the audit, the scores and the ranked list of what to fix before
          you&apos;ve finished reading this page.
        </p>
        <div className="lp-cta-actions">
          <Link className="btn lp-btn-lg" href={primaryHref}>
            {primaryLabel} →
          </Link>
          <Link className="btn btn-ghost lp-btn-lg" href="/#plans">
            See what it costs
          </Link>
        </div>
      </div>

      <footer className="lp-section lp-footer">
        <div className="lp-footer-grid">
          <div className="lp-footer-brand">
            <div className="brand">
              <span className="brand-mark" />
              <span className="brand-name">Signal</span>
            </div>
            <p>Diagnosis and fix in one place — audits, rankings, and AI-assisted fixes for your own pages.</p>
          </div>
          <div className="lp-footer-cols">
            <div className="lp-footer-col">
              <h5>Product</h5>
              <Link href="/#features">Features</Link>
              <Link href="/#how">How it works</Link>
              <Link href="/#plans">Pricing</Link>
              <Link href="/auto-seo-tools">Auto SEO tools</Link>
            </div>
            <div className="lp-footer-col">
              <h5>Account</h5>
              <Link href="/login">Log in</Link>
              <Link href="/login?mode=register">Create account</Link>
            </div>
            <div className="lp-footer-col">
              <h5>Legal &amp; contact</h5>
              <Link href="/terms">Terms of Service</Link>
              <Link href="/privacy">Privacy Policy</Link>
              <Link href="/refunds">Refund Policy</Link>
              <a href={`mailto:${SUPPORT_EMAIL}`}>Contact</a>
            </div>
          </div>
        </div>
        <div className="lp-footer-bottom">SIGNAL · SEO AUDITS, RANK TRACKING &amp; AI FIXES IN ONE APP</div>
      </footer>
    </div>
  );
}
