# Signal — Self-Serve SEO Platform
Product & Technical Requirements

---

## 1. Overview

Signal is a website that lets users manage SEO for their own web pages without an
agency. Users add sites and pages, run audits, see an optimization score, track
keyword rankings, and get actionable fixes — including AI-generated suggestions.

**Primary user:** small business owners, indie site owners, marketers, and
agencies managing SEO for one or more sites.

**Core loop:** add site → audit pages → see score + prioritized issues → fix
issues (manually or via AI suggestion) → re-scan → track ranking movement over
time.

---

## 2. Core Features

### 2.1 Site & Page Management
- User adds a website (domain verification via DNS TXT record, meta tag, or
  file upload — same pattern as Google Search Console)
- Add/import individual pages/URLs under a site
- Dashboard: all sites → all pages, each with an overall SEO health score
  (0–100)

### 2.2 On-Page SEO Audit *(free tier)*
Runs on page HTML that Signal fetches itself — no external API cost, so this
stays free:
- Title tag: presence, length, keyword match, duplicates across site
- Meta description: presence, length
- Heading structure: H1 uniqueness, H1–H6 hierarchy
- Image alt text coverage
- Internal/external link analysis
- Content length & keyword density vs. target keyword
- Readability score
- Canonical tag, robots meta tag, structured data (schema.org) presence
- **Output:** checklist per page, each item pass/warning/fail with a plain-
  language description and (where relevant) a suggested fix

### 2.3 Technical SEO *(free tier, except CWV re-checks — see §3)*
- Crawlability: robots.txt and sitemap.xml presence/validity
- Page speed & Core Web Vitals (via Google PageSpeed Insights API)
- Mobile-friendliness
- Broken links (404s), redirect chains
- SSL/HTTPS check
- Indexability status (confirmed via Google Search Console API where
  connected)

### 2.4 Keyword & Ranking *(paid — see §3)*
- User assigns one or more target keywords per page
- Rank tracking over time via a third-party rank-data provider
- Keyword suggestions (search volume, difficulty)
- Competitor comparison for the same keyword

### 2.5 Progress & Reporting
- Per-page optimization score (0–100), recalculated on each scan
- Historical trend charts: score over time, rank over time, traffic (if GA
  connected)
- Prioritized to-do list, sorted by estimated impact

### 2.6 Integrations
- Google Search Console — impressions, clicks, indexing status
- Google Analytics — traffic correlation with score/ranking changes

### 2.7 v2 / Later
- AI content brief generator based on top-ranking competitors
- Backlink monitoring
- Multi-user / team / agency mode (manage multiple clients)
- Scheduled automated re-audits with email/Slack alerts
- White-label PDF reports

---

## 3. Monetization

Costed external calls (rank checks, AI generations) are gated. Audits that
only require parsing a page Signal already fetched stay free — that's the
product's free hook.

### 3.1 Free vs. paid

| Free forever | Paid |
|---|---|
| On-page audit (title, meta, H1, alt text, links) | Keyword rank checks / re-checks |
| Basic technical checks (robots.txt, sitemap, SSL) | AI-generated suggestions (meta descriptions, content briefs) |
| Manual rescan, throttled to 1x/day | On-demand / unlimited rescans |
| 1 site, up to 5 pages | Additional sites / pages |
| 3 tracked keywords | Additional tracked keywords, competitor tracking |
| — | Historical trend data beyond 7 days |
| — | Scheduled automated audits + alerts |
| — | White-label PDF export |
| — | Team seats / multi-user |

### 3.2 Billing model

> **Superseded (2026-09-19).** The tier table below was the original intent. Signal now
> sells **credits and nothing else**: one tier, the same limits for everyone, and
> one-time credit packs the owner creates and prices in `/admin/pricing`. Everything
> that costs Signal money was already metered in credits, so the tiers were charging for
> storage rather than for cost. See `plan.md` Phase I; the live catalog is whatever
> `GET /pricing` returns.

Hybrid: subscription tiers for baseline usage + credit packs for burst usage,
mirroring how Signal itself is billed by its own data providers.

| Tier | Price (draft) | Includes |
|---|---|---|
| Free | $0 | 1 site, 5 pages, on-page + technical audits, 3 tracked keywords, 3 rank checks/mo, 3 AI suggestions/mo, daily manual rescan |
| Pro | $24/mo | 5 sites, 50 pages, unlimited rescans, 50 tracked keywords, weekly auto rank-refresh, 100 AI suggestions/mo |
| Agency | $89/mo | Unlimited sites, white-label reports, team seats, daily rank refresh, unlimited AI suggestions |

**Credit packs** (on top of any tier): e.g. 50 credits for $9.
- 1 credit = 1 keyword rank check
- 1 credit = 1 AI suggestion generation

### 3.3 Billing implementation

> **Update (2026-09-19):** payments are collected through **Dodo Payments** (a merchant of
> record, chosen because Stripe accounts are invite-only in India), not Stripe, and there
> are no subscriptions to manage — only one-time credit packs. The rest of this section
> describes intent; what's built is documented in `plan.md` Phases H and I and
> `backend/README.md` "Billing & admin".
- **Stripe** — Billing for subscriptions, Checkout for credit packs, Customer
  Portal for self-serve plan management/cancellation
- Required keys: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`,
  `STRIPE_WEBHOOK_SECRET`
- `users` table needs `plan` and `credits_balance` fields
- Before any credit-consuming action: check balance → decrement on success →
  if zero, show upgrade/buy-credits prompt (see §5 UI)
- Dedicated webhook endpoint handling `checkout.session.completed`,
  `invoice.paid`, `customer.subscription.deleted`, with Stripe signature
  verification
- Log every credit-consuming action (type, timestamp, cost) for abuse
  prevention and margin tracking
- **Open question:** is `credits_balance` shared per user, or scoped per
  site? Per-user is simpler; per-site matters for agencies billing credits
  back to individual clients. Needs a decision before the schema is final.

---

## 4. Tech Stack

Backend language decision: **Python**, over Go, because Signal's roadmap
depends on AI-agent features (AI suggestions, content briefs), and Python's
AI/agent ecosystem (Anthropic/OpenAI SDKs, LangChain, LlamaIndex) is far more
mature than Go's. Go would win on raw crawl concurrency, but that's not the
bottleneck here — a specific crawler component could be peeled into a Go
service later if it ever becomes one.

| Layer | Choice | Why |
|---|---|---|
| API | Python, FastAPI | async, typed, free OpenAPI docs |
| Background jobs | Celery + Redis (or RQ for simpler setups) | audits/crawls are slow, must run async |
| Page rendering / audits | Playwright (Python) | mature Python support, can also drive Lighthouse |
| Database | PostgreSQL + SQLAlchemy/SQLModel | relational fit for sites/pages/audits/history |
| Frontend | Next.js (React) | SSR for marketing pages, good dashboard DX |
| Auth | Clerk or NextAuth | don't build auth from scratch |
| Billing | Stripe | see §3.3 |
| Frontend hosting | Vercel | |
| Backend hosting | Railway / Render / AWS | needs persistent process for Playwright + workers, not pure serverless |

---

## 5. External Services & API Keys

| Service | Purpose | Cost |
|---|---|---|
| Google Search Console API | Indexing status, impressions, clicks, queries | Free (OAuth) |
| Google Analytics Data API | Traffic correlation | Free (OAuth) |
| Google PageSpeed Insights API | Core Web Vitals, performance score | Free |
| DataForSEO or SerpApi | Keyword rank tracking, volume, competitor data | Paid, usage-based — primary variable cost |
| Anthropic (Claude) API | AI-generated suggestions, content briefs | Paid, per-token |
| Resend or SendGrid | Email notifications (audit complete, rank drop alerts) | Free tier available |
| Stripe | Billing | Transaction fee |
| Domain verification | Self-built (DNS TXT / file upload) | No external key |

---

## 6. UI / Design Direction

Full interactive mockup: `frontend/seo-dashboard-mockup.html`

- **Concept:** SEO tooling framed as a diagnostic/scanning instrument rather
  than a generic SaaS dashboard — the audit is a "scan," the score is a
  gauge, issues are flagged by signal color, not decorative cards.
- **Palette:** deep charcoal-navy background (`#10161C`), signal-cyan accent
  (`#4FD1C5`), amber for warnings (`#E8A33D`), muted coral for critical
  issues (`#E85D6E`).
- **Type:** Space Grotesk for headlines/scores, Inter for body/UI text.
- **Layout:** sidebar (sites + plan/usage widget) + main panel (score gauge,
  stat row, prioritized fixes, pages table). Page detail view: checklist with
  inline fixes + keyword tracking panel.
- **Paywall pattern:** metered features (rank checks, AI suggestions) show
  live usage bars in the sidebar; hitting a limit opens a modal offering
  either a plan upgrade or a one-off credit pack, not a hard block with no
  path forward.

---

## 7. Open Questions

- [ ] Are `credits_balance` and rank/AI usage tracked per-user or per-site?
- [ ] Which rank-data provider (DataForSEO vs. SerpApi) — needs a cost
      comparison at expected query volume before committing.
- [ ] Exact free-tier limits (3 keywords / 5 pages / 3 credits-worth of
      rank checks & AI suggestions per month) — placeholders, validate
      against provider costs before launch.
- [ ] Agency tier: how are team seats and per-client billing structured?

---

## 8. Suggested Build Order

1. Database schema: sites, pages, audits, checks, keyword_ranks, users,
   plan/credits
2. FastAPI scaffold + auth
3. On-page audit engine (no external APIs needed — ship this first)
4. Scoring logic + dashboard wired to real data
5. Stripe integration (plans + credits + webhooks)
6. Keyword rank tracking (external provider integration)
7. AI suggestions (Claude API)
8. GSC / GA integrations
9. Scheduled audits, alerts, white-label reports (v2)
