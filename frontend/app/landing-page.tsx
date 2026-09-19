"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { formatRate, formatUsd, limitLabel } from "@/lib/format";
import { SUPPORT_EMAIL } from "@/lib/site";
import type { Pricing, PricingCreditPack } from "@/lib/types";

// What one credit actually buys. These are the real deduction points in
// backend/app/routers/{keywords,suggestions}.py - keep them in step, because
// this is the only place a visitor learns what they're paying for.
const CREDIT_COSTS: { label: string; credits: number }[] = [
  { label: "Track a keyword, or re-check its rank", credits: 1 },
  { label: "See who outranks you for a keyword", credits: 1 },
  { label: "Any AI fix: title, meta, headings, alt text, internal links", credits: 1 },
  { label: "Keyword opportunities for a page", credits: 2 },
  { label: "A full ranking action plan", credits: 2 },
  { label: "Find keyword ideas for a site", credits: 2 },
  { label: "Check one keyword in Google and in AI answers", credits: 2 },
];

export default function LandingPage({ pricing }: { pricing: Pricing }) {
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
            <a href="#features">Features</a>
            <a href="#how">How it works</a>
            <a href="#plans">Pricing</a>
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

      <div className="lp-hero">
        <div>
          <div className="lp-eyebrow">Live on your sites right now</div>
          <h1>
            Every SEO problem, <em>ranked and ready to fix</em> — without leaving the app.
          </h1>
          <p className="lp-hero-sub">
            Signal audits your pages, tracks rankings against real competitors, and pulls in your actual Google
            Search Console data — then turns all of it into one prioritized list you can act on and verify, right
            here.
          </p>
          <div className="lp-hero-ctas">
            <Link className="btn lp-btn-lg" href={primaryHref}>
              {primaryLabel} →
            </Link>
            {!user && (
              <Link className="btn btn-ghost lp-btn-lg" href="/login">
                Log in
              </Link>
            )}
          </div>
          <div className="lp-hero-note">FREE TO USE · NO SUBSCRIPTION · NO CARD REQUIRED</div>
        </div>

        <div className="lp-hero-visual">
          <div className="lp-device-panel">
            <div className="lp-device-chrome">
              <span className="lp-device-dot" />
              <span className="lp-device-dot" />
              <span className="lp-device-dot" />
              <span className="lp-device-url">signal.app/sites/2</span>
            </div>
            <div className="lp-panel-grid">
              <div className="lp-gauge-card">
                <div className="lp-gauge-label">SITE SCORE</div>
                <div className="lp-gauge-wrap">
                  <svg viewBox="0 0 96 96">
                    <circle className="lp-gauge-ring-bg" cx="48" cy="48" r="40" />
                    <circle
                      className="lp-gauge-ring-fg"
                      cx="48"
                      cy="48"
                      r="40"
                      strokeDasharray="251.2"
                      strokeDashoffset="55.3"
                    />
                  </svg>
                  <div className="lp-gauge-value">
                    <b>78</b>
                    <span>/ 100</span>
                  </div>
                </div>
                <div className="lp-gauge-delta">▲ +9 this month</div>
              </div>
              <div className="lp-mini-checks">
                <div className="lp-mini-check">
                  <span className="lp-mini-check-name">Title tag</span>
                  <span className="lp-pill good">Pass</span>
                </div>
                <div className="lp-mini-check">
                  <span className="lp-mini-check-name">Meta description</span>
                  <span className="lp-pill warn">Warn</span>
                </div>
                <div className="lp-mini-check">
                  <span className="lp-mini-check-name">Image alt text</span>
                  <span className="lp-pill bad">Fail</span>
                </div>
              </div>
            </div>
            <div className="lp-mini-opp">
              <div className="lp-mini-opp-text">
                <b>Meta description missing — /pricing</b>
                <span>Severity: high · suggested fix ready</span>
              </div>
              <span className="lp-badge-applying">Applied — verifying</span>
            </div>
          </div>
          <div className="lp-hero-float">
            <span className="lp-mono" style={{ color: "var(--good)" }}>
              ▲
            </span>
            <span>
              Keyword <b>&quot;seo audit tool&quot;</b> moved #34 → <b>#9</b>
            </span>
          </div>
        </div>
      </div>

      <section id="features" className="lp-section lp-features">
        <div className="lp-feature-row">
          <div className="lp-feature-rail">
            <span className="dot" />
            <span className="line" />
          </div>
          <div className="lp-feature-copy">
            <div className="lp-feature-tag">On-page audits</div>
            <h3>Eleven checks, one score, zero API cost.</h3>
            <p>
              Every page gets scored 0–100 on title tag, meta description, heading structure, image alt text,
              internal/external links, content length, keyword density, readability, canonical tag, robots meta,
              and structured data — recalculated on every scan.
            </p>
            <ul className="lp-feature-list">
              <li>Rescan any page any time — audits never cost a credit</li>
              <li>Each failing check ships with a suggested fix, not just a red X</li>
            </ul>
          </div>
          <div className="lp-feature-visual">
            <div className="lp-visual-label">
              <span>CHECKLIST — /blog/keyword-research</span>
              <span>4 of 11</span>
            </div>
            <div className="lp-vc-grid">
              <div className="lp-vc-check">
                <div className="lp-vc-check-top">
                  <span className="lp-vc-check-name">Title tag</span>
                  <span className="lp-pill good">Pass</span>
                </div>
              </div>
              <div className="lp-vc-check">
                <div className="lp-vc-check-top">
                  <span className="lp-vc-check-name">Headings</span>
                  <span className="lp-pill warn">Warn</span>
                </div>
              </div>
              <div className="lp-vc-check">
                <div className="lp-vc-check-top">
                  <span className="lp-vc-check-name">Alt text</span>
                  <span className="lp-pill bad">Fail</span>
                </div>
              </div>
              <div className="lp-vc-check">
                <div className="lp-vc-check-top">
                  <span className="lp-vc-check-name">Structured data</span>
                  <span className="lp-pill good">Pass</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="lp-feature-row full">
          <div className="lp-feature-rail">
            <span className="dot" />
            <span className="line" />
          </div>
          <div className="lp-feature-full-body">
            <div className="lp-feature-copy">
              <div className="lp-feature-tag">
                Keyword tracking &amp; competition
                <span className="lp-spotlight-flag">Deep dive</span>
              </div>
              <h3>See exactly what it takes to outrank them — then track the climb.</h3>
              <p>
                Track keywords per page with a location and device picker, watch rank history against the
                competitors actually holding those spots, and — for anything not ranking yet — get an AI action
                plan built from what&apos;s working for the pages beating you.
              </p>
              <ul className="lp-feature-list">
                <li>&quot;Recheck rankings now&quot; refreshes every tracked keyword on a page at once</li>
                <li>Competitor comparison excludes your own domain automatically, powered by SerpApi or DataForSEO</li>
              </ul>
            </div>
            <div className="lp-spotlight-grid">
              <div className="lp-feature-visual">
                <div className="lp-visual-label">
                  <span>RANK HISTORY — &quot;seo audit tool&quot;</span>
                  <span>6 checks</span>
                </div>
                <div className="lp-chart-box">
                  <svg viewBox="0 0 320 130">
                    <line x1="0" y1="10" x2="320" y2="10" stroke="var(--border-soft)" strokeWidth="1" />
                    <line x1="0" y1="65" x2="320" y2="65" stroke="var(--border-soft)" strokeWidth="1" />
                    <line x1="0" y1="120" x2="320" y2="120" stroke="var(--border-soft)" strokeWidth="1" />
                    <path
                      d="M0,20 L64,32 L128,58 L192,70 L256,96 L320,108 L320,130 L0,130 Z"
                      fill="var(--accent-dim)"
                      opacity="0.5"
                    />
                    <path
                      d="M0,20 L64,32 L128,58 L192,70 L256,96 L320,108"
                      fill="none"
                      stroke="var(--accent)"
                      strokeWidth="2.5"
                    />
                    <circle cx="320" cy="108" r="4.5" fill="var(--accent)" />
                    <path
                      d="M0,86 L64,84 L128,80 L192,79 L256,76 L320,74"
                      fill="none"
                      stroke="var(--text-faint)"
                      strokeWidth="1.5"
                      strokeDasharray="3 4"
                    />
                    <text x="4" y="10" fill="var(--text-faint)" fontFamily="var(--font-mono)" fontSize="9">
                      #1
                    </text>
                    <text x="4" y="120" fill="var(--text-faint)" fontFamily="var(--font-mono)" fontSize="9">
                      #42
                    </text>
                    <text
                      x="278"
                      y="103"
                      fill="var(--accent)"
                      fontFamily="var(--font-mono)"
                      fontSize="10"
                      fontWeight="600"
                    >
                      #9
                    </text>
                    <text x="255" y="70" fill="var(--text-faint)" fontFamily="var(--font-mono)" fontSize="9">
                      top rival ~#4
                    </text>
                  </svg>
                </div>
                <div className="lp-comp-row you">
                  <span className="rank">#9</span>
                  <span>signalapp.io — you</span>
                </div>
                <div className="lp-comp-row">
                  <span className="rank lp-mono">#4</span>
                  <span>ahrefs.com/blog/seo-audit</span>
                </div>
                <div className="lp-comp-row">
                  <span className="rank lp-mono">#3</span>
                  <span>semrush.com/seo-audit-tool</span>
                </div>
                <div className="lp-comp-row">
                  <span className="rank lp-mono">#6</span>
                  <span>moz.com/learn/seo/audit</span>
                </div>
              </div>
              <div className="lp-spotlight-stack">
                <div className="lp-spot-card">
                  <div className="lp-visual-label">
                    <span>ACTION PLAN — &quot;seo audit checklist&quot;</span>
                    <span>not ranking</span>
                  </div>
                  <div className="lp-spot-card-body">
                    Every top-5 result for this term pairs the concept with a step-by-step checklist and a
                    downloadable template — your page covers the idea but never uses <b>&quot;checklist&quot;</b> in
                    a heading. Add a numbered checklist section and target it in an H2.
                  </div>
                </div>
                <div className="lp-spot-card">
                  <div className="lp-visual-label">
                    <span>KEYWORD OPPORTUNITIES</span>
                    <span>related to &quot;seo audit tool&quot;</span>
                  </div>
                  <div className="lp-kw-opp-row">
                    <div className="lp-kw-opp-text">
                      <b>seo audit checklist</b>
                      <span>high overlap — no page targets it yet</span>
                    </div>
                    <span className="lp-add-btn">+ Add</span>
                  </div>
                  <div className="lp-kw-opp-row">
                    <div className="lp-kw-opp-text">
                      <b>free seo audit online</b>
                      <span>competitors rank top 3 for this</span>
                    </div>
                    <span className="lp-add-btn">+ Add</span>
                  </div>
                  <div className="lp-kw-opp-row">
                    <div className="lp-kw-opp-text">
                      <b>core web vitals checker</b>
                      <span>related intent, zero coverage</span>
                    </div>
                    <span className="lp-add-btn">+ Add</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="lp-feature-row">
          <div className="lp-feature-rail">
            <span className="dot" />
            <span className="line" />
          </div>
          <div className="lp-feature-copy">
            <div className="lp-feature-tag">AI-assisted fixes</div>
            <h3>Suggestions that already know your page.</h3>
            <p>
              One click generates a rewritten meta description, title tag, heading outline, simplified copy for
              low-readability sections, alt text for every unlabeled image, and internal-link suggestions against
              your own site&apos;s other pages — from OpenAI or Anthropic, your choice.
            </p>
            <ul className="lp-feature-list">
              <li>Every suggestion is generated from your actual content and target keyword</li>
              <li>No sibling pages to link to? The AI call — and the credit — is skipped automatically</li>
            </ul>
          </div>
          <div className="lp-feature-visual">
            <div className="lp-visual-label">
              <span>META DESCRIPTION — /widgets</span>
              <span />
            </div>
            <div className="lp-rewrite-block before">
              <div className="lp-rewrite-head">Before</div>
              <div className="lp-rewrite-body">Cheap widgets for sale. Buy now.</div>
            </div>
            <div className="lp-rewrite-block after">
              <div className="lp-rewrite-head">AI suggestion</div>
              <div className="lp-rewrite-body">
                Shop affordable widgets built to last — free shipping on every order, ships same day from Signal.
              </div>
            </div>
            <div className="lp-copy-affordance">⧉ copy to clipboard</div>
          </div>
        </div>

        <div className="lp-feature-row reverse">
          <div className="lp-feature-rail">
            <span className="dot" />
            <span className="line" />
          </div>
          <div className="lp-feature-copy">
            <div className="lp-feature-tag">Opportunities &amp; verified fixes</div>
            <h3>One queue for the whole site. Mark it applied — we check it stuck.</h3>
            <p>
              Failing checks and ranking problems across every page land in one severity-sorted list. Apply a fix
              yourself, click &quot;Mark as applied,&quot; and the next audit or rank check verifies it
              automatically — no manual follow-up.
            </p>
            <ul className="lp-feature-list">
              <li>A resolved fix raises an in-app alert the moment it&apos;s confirmed</li>
              <li>Keywords with no rank get an AI competitor-gap action plan, not just a suggestion to try something else</li>
            </ul>
          </div>
          <div className="lp-feature-visual">
            <div className="lp-visual-label">
              <span>OPPORTUNITIES — signalapp.io</span>
              <span>3 open</span>
            </div>
            <div className="lp-opp-steps">
              <div className="lp-opp-step">
                <div className="lp-opp-step-text">
                  <b>Meta description missing — /pricing</b>
                  <span>audit_fail</span>
                </div>
                <span className="lp-opp-badge high">High</span>
              </div>
              <div className="lp-opp-step">
                <div className="lp-opp-step-text">
                  <b>Applied by you — checking next scan</b>
                  <span>rank_drop · /blog/roi</span>
                </div>
                <span className="lp-opp-badge pending">Verifying</span>
              </div>
              <div className="lp-opp-step">
                <div className="lp-opp-step-text">
                  <b>Verified fixed — score +14</b>
                  <span>audit_fail · /returns</span>
                </div>
                <span className="lp-opp-badge done">Resolved</span>
              </div>
            </div>
          </div>
        </div>

        <div className="lp-feature-row">
          <div className="lp-feature-rail">
            <span className="dot" />
            <span className="line" />
          </div>
          <div className="lp-feature-copy">
            <div className="lp-feature-tag">Site health rollup</div>
            <h3>Your site&apos;s score over time — and exactly what moved it.</h3>
            <p>
              A blended trend line reconstructed from your full audit history, plus the biggest per-page score
              swings and per-keyword rank movements between your two most recent checks — wins included, not just
              drops.
            </p>
            <ul className="lp-feature-list">
              <li>No new API calls — pure aggregation of data you already have</li>
              <li>Newly-found and newly-lost keyword rankings are called out explicitly</li>
            </ul>
          </div>
          <div className="lp-feature-visual">
            <div className="lp-visual-label">
              <span>SITE HEALTH — 90 days</span>
              <span>78 / 100</span>
            </div>
            <div className="lp-chart-box">
              <svg viewBox="0 0 320 90">
                <path
                  d="M0,58 L45,48 L90,56 L135,32 L180,20 L225,26 L270,16 L320,10"
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth="2.5"
                />
                <circle cx="320" cy="10" r="4" fill="var(--accent)" />
              </svg>
            </div>
            <div className="lp-health-rows">
              <div className="lp-health-row">
                <span>/blog/roi score</span>
                <span className="lp-health-move up">▲ +14</span>
              </div>
              <div className="lp-health-row">
                <span>&quot;free seo tool&quot; keyword</span>
                <span className="lp-health-move up">▲ #34 → #9</span>
              </div>
              <div className="lp-health-row">
                <span>/returns score</span>
                <span className="lp-health-move down">▼ −11</span>
              </div>
            </div>
          </div>
        </div>

        <div className="lp-feature-row full">
          <div className="lp-feature-rail">
            <span className="dot" />
          </div>
          <div className="lp-feature-full-body">
            <div className="lp-feature-copy">
              <div className="lp-feature-tag">
                Google Search Console &amp; Analytics
                <span className="lp-spotlight-flag">Deep dive</span>
              </div>
              <h3>Real impressions and clicks — not an estimate of them.</h3>
              <p>
                Connect your Google account once and map each site to its Search Console property and GA4
                property. See how impressions and clicks have actually trended, exactly which queries drove them,
                and whether the page is even indexed — the real answer when it ranks nowhere because it&apos;s
                simply not been crawled.
              </p>
              <ul className="lp-feature-list">
                <li>Doesn&apos;t cost Signal credits — free once the OAuth grant exists</li>
                <li>A different, complementary signal to rank tracking: this shows what people actually searched</li>
              </ul>
            </div>
            <div className="lp-feature-visual">
              <div className="lp-visual-label">
                <span>SEARCH CONSOLE — /blog/roi</span>
                <span>8 weeks</span>
              </div>
              <div className="lp-chart-box">
                <svg viewBox="0 0 320 100">
                  <line x1="0" y1="20" x2="320" y2="20" stroke="var(--border-soft)" strokeWidth="1" />
                  <line x1="0" y1="56" x2="320" y2="56" stroke="var(--border-soft)" strokeWidth="1" />
                  <path
                    d="M0,63 L46,60 L91,56 L137,50 L183,45 L229,40 L274,32 L320,27 L320,96 L0,96 Z"
                    fill="var(--text-faint)"
                    opacity="0.16"
                  />
                  <path
                    d="M0,63 L46,60 L91,56 L137,50 L183,45 L229,40 L274,32 L320,27"
                    fill="none"
                    stroke="var(--text-faint)"
                    strokeWidth="2"
                  />
                  <path
                    d="M0,73 L46,71 L91,66 L137,62 L183,55 L229,50 L274,42 L320,32"
                    fill="none"
                    stroke="var(--accent)"
                    strokeWidth="2.5"
                  />
                  <circle cx="320" cy="27" r="3.5" fill="var(--text-faint)" />
                  <circle cx="320" cy="32" r="4.5" fill="var(--accent)" />
                </svg>
              </div>
              <div className="lp-chart-legend">
                <span className="lp-legend-dot muted">
                  Impressions <b>420 → 940</b>
                </span>
                <span className="lp-legend-dot">
                  Clicks <b>28 → 88</b>
                </span>
              </div>
              <div className="lp-gsc-lower">
                <div className="lp-stat-row4 compact">
                  <div className="lp-stat-tile">
                    <div className="n lp-mono">4.2</div>
                    <div className="l">Avg. position</div>
                  </div>
                  <div className="lp-stat-tile">
                    <div className="n lp-mono">9.4%</div>
                    <div className="l">CTR</div>
                  </div>
                  <div className="lp-stat-tile">
                    <div className="n lp-mono">2,310</div>
                    <div className="l">Pageviews (GA4)</div>
                  </div>
                  <div className="lp-stat-tile">
                    <div className="n lp-mono">2m14s</div>
                    <div className="l">Avg. session</div>
                  </div>
                </div>
                <table className="lp-gsc-table">
                  <thead>
                    <tr>
                      <th>Query</th>
                      <th style={{ textAlign: "right" }}>Clicks</th>
                      <th style={{ textAlign: "right" }}>Position</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>seo roi calculator</td>
                      <td className="num">142</td>
                      <td className="num">4.2</td>
                    </tr>
                    <tr>
                      <td>how to measure seo return</td>
                      <td className="num">61</td>
                      <td className="num">7.8</td>
                    </tr>
                    <tr>
                      <td>seo reporting template</td>
                      <td className="num">39</td>
                      <td className="num">11.3</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="lp-section lp-strip">
        <div className="lp-strip-item">
          <div className="lp-strip-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.3-4.3" />
            </svg>
          </div>
          <div>
            <h4>Give it your domain, not a list of URLs</h4>
            <p>
              Signal reads your sitemap — or follows your own links when there isn’t one — and tells you which
              pages Google has actually indexed. A page that isn’t indexed can’t rank, whatever its score says.
            </p>
          </div>
        </div>
        <div className="lp-strip-item">
          <div className="lp-strip-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
              <path d="M18 16l.8 2.2L21 19l-2.2.8L18 22l-.8-2.2L15 19l2.2-.8z" />
            </svg>
          </div>
          <div>
            <h4>Visibility in AI answers, not just Google</h4>
            <p>
              For every keyword you target, see where you rank in Google, whether its AI Overview cites you — and
              who it cited instead — and whether an AI assistant names you when asked.
            </p>
          </div>
        </div>
        <div className="lp-strip-item">
          <div className="lp-strip-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <path d="M3 9h18" />
            </svg>
          </div>
          <div>
            <h4>Alerts on verified fixes</h4>
            <p>Mark a fix as applied and Signal alerts you in-app the moment your next scan confirms it worked.</p>
          </div>
        </div>
        <div className="lp-strip-item">
          <div className="lp-strip-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6z" />
            </svg>
          </div>
          <div>
            <h4>Domain ownership verification</h4>
            <p>Prove you own a site via DNS TXT record, meta tag, or hosted file — the same three options Search Console itself offers.</p>
          </div>
        </div>
        <div className="lp-strip-item">
          <div className="lp-strip-icon">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M17 2l4 4-4 4" />
              <path d="M3 12v-2a4 4 0 014-4h14" />
              <path d="M7 22l-4-4 4-4" />
              <path d="M21 12v2a4 4 0 01-4 4H3" />
            </svg>
          </div>
          <div>
            <h4>Not locked to one vendor</h4>
            <p>Rank data from SerpApi or DataForSEO, AI from OpenAI or Anthropic — swap either with one config value, no code changes.</p>
          </div>
        </div>
      </div>

      <section id="how" className="lp-section lp-steps">
        <div className="lp-section-head center">
          <div className="lp-kicker">How it works</div>
          <h2>From a bare domain to a prioritized fix list in three steps.</h2>
        </div>
        <div className="lp-steps-grid">
          <div className="lp-step">
            <div className="lp-step-num">1</div>
            <h4>Add your site and pages</h4>
            <p>Verify ownership, and Signal crawls and audits every page instantly — no waiting period.</p>
          </div>
          <div className="lp-step">
            <div className="lp-step-num">2</div>
            <h4>Get your opportunities list</h4>
            <p>Every failing check and ranking issue across the whole site, ranked by severity, in one place.</p>
          </div>
          <div className="lp-step">
            <div className="lp-step-num">3</div>
            <h4>Fix it, mark it applied</h4>
            <p>Apply the fix yourself, tell Signal, and the next scan confirms whether it actually worked.</p>
          </div>
        </div>
      </section>

      <section id="plans" className="lp-section lp-plans">
        <div className="lp-section-head center">
          <div className="lp-kicker">Pricing</div>
          <h2>Free to use. Pay only for the expensive parts.</h2>
          <p>
            Audits, the opportunities list and everything in the dashboard are free and unlimited. Credits cover the
            work that costs real money on our side — live rank lookups and AI writing. They never expire, and there is
            no subscription.
          </p>
        </div>

        <div className="lp-free-band">
          <div>
            <div className="lp-free-title">Every account, free</div>
            <ul className="lp-free-list">
              <li>
                <b>{limitLabel(pricing.limits.max_sites)}</b> sites
              </li>
              <li>
                <b>{limitLabel(pricing.limits.max_pages_per_site)}</b> pages per site
              </li>
              <li>
                <b>{limitLabel(pricing.limits.max_keywords_per_page)}</b> tracked keywords per page
              </li>
              <li>Unlimited audits, scores and opportunity lists</li>
              <li>Finding your pages, and checking which Google has indexed</li>
              <li>Google Search Console + Analytics, connected free</li>
            </ul>
          </div>
          <div>
            <div className="lp-free-title">What a credit buys</div>
            <ul className="lp-credit-costs">
              {CREDIT_COSTS.map((item) => (
                <li key={item.label}>
                  <span className="lp-credit-cost lp-mono">{item.credits}</span>
                  {item.label}
                </li>
              ))}
            </ul>
            <p className="lp-free-foot">
              New accounts start with <b>{pricing.signup_credits} free credits</b> — no card needed.
            </p>
          </div>
        </div>

        {/* Packs come from GET /pricing, which the owner edits in /admin/pricing;
            there can be any number of them, so this grid adapts. */}
        <div className="lp-packs-grid" data-count={pricing.credit_packs.length}>
          {pricing.credit_packs.map((pack) => (
            <PackCard key={pack.key} pack={pack} user={!!user} />
          ))}
        </div>

        <p className="lp-plans-note">
          Prices in USD, one-time — credits are added to your balance and do not expire. Payments are handled by Dodo
          Payments, our merchant of record, which adds sales tax/VAT where required. See our{" "}
          <Link href="/refunds">refund policy</Link> and <Link href="/terms">terms</Link>.
        </p>
      </section>

      <div className="lp-section lp-cta-band">
        <h2>See your first opportunities list in under two minutes.</h2>
        <p>Add a site, verify it, and Signal has your full audit and action list ready before you&apos;ve finished reading it.</p>
        <div className="lp-cta-actions">
          <Link className="btn lp-btn-lg" href={primaryHref}>
            {primaryLabel} →
          </Link>
          {!user && (
            <Link className="btn btn-ghost lp-btn-lg" href="/login">
              Log in
            </Link>
          )}
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
              <a href="#features">Features</a>
              <a href="#how">How it works</a>
              <a href="#plans">Pricing</a>
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

function PackCard({ pack, user }: { pack: PricingCreditPack; user: boolean }) {
  const perCredit = pack.price_per_credit_cents;

  return (
    <div className={`lp-pack-card ${pack.badge ? "featured" : ""}`}>
      <div className="lp-plan-top">
        <span className="lp-plan-name">{pack.name}</span>
        {pack.badge && <span className="lp-plan-flag">{pack.badge}</span>}
      </div>
      <div className="lp-plan-price lp-mono">{formatUsd(pack.price_cents)}</div>
      <div className="lp-pack-rate lp-mono">
        {pack.credits} credits{perCredit ? ` · ${formatRate(perCredit)} each` : ""}
      </div>
      {pack.description && <p className="lp-pack-desc">{pack.description}</p>}
      {pack.purchasable ? (
        <Link className="btn lp-btn-block" href={user ? "/dashboard/billing" : "/login?mode=register"}>
          {user ? "Buy credits" : "Sign up to buy"}
        </Link>
      ) : (
        <span className="btn btn-ghost lp-btn-block" style={{ cursor: "default", opacity: 0.8 }}>
          Coming soon
        </span>
      )}
    </div>
  );
}
