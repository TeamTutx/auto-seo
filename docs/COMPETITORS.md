# Competitive landscape

Where Signal sits against the incumbents, and which gaps are worth closing.

Semrush figures below were read from semrush.com/prices and /features on
**20 September 2026**. They restructure often — the whole product was rebuilt
around AI search some time before that date — so re-check before quoting them.

---

## Semrush

**What it is:** a data-index business, not an audit tool. The moat is three
expensive assets: a crawled backlink index, a keyword database with search
volumes, and (new) a system that monitors what LLMs say about brands. Everything
else is tooling on top of those.

**Pricing:** $139 / $199 / $299 / $549 per month (SEO, Starter, Pro+, Advanced),
~17% off annually. Extra seats $45/mo each. Reports $10–20/mo. Enterprise is
custom. Entry cost is **$1,668/year**.

**Strategic note:** every tier now sells "prompts tracked daily" and AI
visibility across ChatGPT, Perplexity, Gemini, Claude and AI Overviews. They are
betting the industry shifts from ranking in Google to being cited by LLMs.

### Feature by feature

| Capability | Signal | Semrush |
|---|---|---|
| On-page audit | 11 checks, 0–100 score | Yes, plus JS rendering, crawl depth, schema gaps |
| Site crawling | **Sitemap + link crawl**, 50/site cap | Full automatic crawl |
| Rank tracking | Per page, location/device, manual, costs a credit | 500–5,000 keywords, daily, automatic |
| Competitor SERP comparison | Yes, per keyword | Yes, plus traffic/domain analytics |
| Keyword research | **Ideas from Search Console, page content and related searches** — still no volume/difficulty | Core product |
| Backlinks | None | Full index, gap analysis, toxicity |
| AI content fixes | 6 types: meta, title, headings, readability, alt text, internal links | Content optimization + full article generation |
| Fix → verify loop | **Yes** — mark applied, next scan confirms it cleared | No |
| Unified prioritised action list | **Yes** — one ranked list | Scattered across ~20 tools |
| GSC + GA4 | Yes, free, per page | Yes, plus a paid reporting add-on |
| AI visibility | **Google AI Overview + ChatGPT** | Also Perplexity, Gemini, Claude |
| Local SEO / listings | None | Yes |
| Digital PR / outreach | None | Yes |
| White-label reports | None | $10–20/mo add-on |
| Team seats | None | $45/mo per user |
| Scheduled audits + alerts | Built, not deployed | Yes |
| Price | $2–$15 one-time | $139–$549/mo |

### Where Signal genuinely wins

- **Price, by two orders of magnitude.** Different market, not a discount. A
  freelancer auditing a few client pages spends a few dollars, not $1,668/year.
- **The fix-and-verify loop.** Semrush tells you the meta description is
  missing. Signal writes it, you apply it, and the next scan confirms the issue
  cleared. Nobody at this price point closes that loop. This is the pitch.
- **No subscription.** Buying $5 of credits to audit a site before launch is a
  ten-second decision. $139/mo is a budget conversation.

### Gaps that actually hurt, ranked

Updated 20 September 2026: 1 and 3 below were the original top gaps and are now
closed by Phase J (see plan.md). What is left:

1. **Metered checks vs daily tracking.** Semrush just updates every morning.
   Signal charges per check, so users ration them and data goes stale. The
   economics are fine; the psychology is bad. The built-but-unprovisioned
   scheduled-audit job is the obvious fix.
2. **No search volumes.** Keyword *discovery* now exists, but the ideas carry no
   volume or difficulty except for the Search Console ones, which are real. That
   is deliberate — inventing estimates would be worse — but it still caps how
   far the "plan my content" story goes. DataForSEO's Labs API is the way in
   when it's worth paying per lookup.
3. **Backlinks.** Unwinnable — an index costs millions. Don't try. Point users
   at Search Console's link report.
4. **AI visibility breadth.** Signal reads Google's AI Overview and ChatGPT;
   Semrush also covers Perplexity, Gemini and Claude. Each extra engine is a new
   vendor account and more credits per run, so this is a pricing decision rather
   than an engineering one.

### Where not to compete

Backlink indexes, keyword databases built from scratch, market/traffic
analytics, digital PR. All are index plays that cost more than this product will
earn for years.

AI visibility was the exception, and Phase J took it: it is a new category where
nobody's index advantage applies, and checking whether an LLM mentions a domain
is just API calls — exactly what the credit model is built for.

---

## Positioning

Semrush is a subscription you justify to a manager. Signal should be something
you buy without asking anyone: point it at a site, get a ranked list of what's
wrong, fix it, and have the tool prove the fix worked.

Don't chase feature parity. The landing page's current framing — "every SEO
problem, ranked and ready to fix" — is the right one.
