# Signal — "one-stop SEO" roadmap

Goal: a user comes to Signal, sees exactly what's wrong with their site's SEO,
and can fix it (or improve keyword targeting) without leaving the app —
diagnosis and fix in one place, not just a report.

Today the app does diagnosis well (on-page audits, keyword rank tracking,
scheduled alerts) and fixes a *little* (AI rewrites for meta description and
title tag only). The gap is turning "here's a list of problems" into "here's
what to do next, and I can do it right here."

## Phase A — Unified "Opportunities" list

**Status: done**

Aggregate what we already store — failing/warning audit checks and
concerning keyword ranks — into one prioritized action list per site. No new
external API calls, no new tables; this is the "come here and see
everything" view everything else hangs off of.

Opportunity types surfaced:
- `audit_fail` / `audit_warning` — a check from the page's latest audit that
  isn't passing, carrying its existing `suggested_fix` text.
- `keyword_not_found` — a tracked keyword's latest rank check came back with
  no position.
- `keyword_low_rank` — ranking, but outside the top 10.
- `keyword_rank_drop` — rank got meaningfully worse since the previous check
  for that keyword.

Backend: `GET /sites/{site_id}/opportunities`, sorted high → low severity.
Frontend: an Opportunities panel on the site overview page, above the pages
table, linking each item to the page (and check/keyword) it's about.

## Phase B — Widen AI-assisted fixes beyond meta/title

**Status: done**

Extended `ai_suggestions.py` and the frontend's `SUGGESTABLE` table (now
kind-aware: text vs. list) to also generate: heading structure outlines
(`/pages/{id}/suggestions/heading`), a simplified rewrite of the opening
passage for low-readability pages (`/suggestions/readability`), per-image
alt text for every `<img>` missing one, batched into a single AI call
(`/suggestions/alt-text`), and internal-linking suggestions against the
page's actual sibling pages on the site (`/suggestions/internal-links`,
skips the AI call entirely - and the credit - when there are no sibling
pages to link to). Same `AIProvider` abstraction throughout. Verified live:
real OpenAI-generated alt text for 8 real Wikipedia images and a genuinely
simpler readability rewrite, both via the actual on-page checklist.

## Phase C — Keyword opportunity discovery

**Status: done**

`POST /pages/{id}/keywords/opportunities` - given a tracked keyword, reuses
the existing competitor SERP lookup (`get_competitors`, no new external API)
plus the page's own content, and asks the AI what related keywords/topics
would close the gap with whoever's outranking it. Shown as a third
"Opportunities" tab next to History/Competitors in `KeywordPanel`, each
suggestion with a one-click "+ Add to tracking" that calls the existing
add-keyword flow. Costs 2 credits (SERP lookup + AI call), charged
separately so an AI failure after a successful lookup doesn't double-charge.
Verified live: real AI-suggested keywords ("SEO techniques", "SEO best
practices", ...) for a tracked "search engine optimization" keyword, added
to tracking and appearing in the main keyword list with a real rank check.

## Phase D — Close the loop: track & verify

**Status: done**

Signal has no write access to a user's actual site, so this is the
"apply changes from the app" story for now: a user applies a suggestion
themselves (copies it into their own CMS/code) and clicks "Mark as applied"
on that opportunity. `POST /pages/{id}/opportunities/apply` records a
baseline (`AppliedFix` table - current audit score, or current rank
position). The next audit or rank check - which already runs on every
manual rescan/recheck, not just Pro/Agency's scheduled ones - automatically
checks pending fixes against the new result and, if resolved, raises an
in-app `fix_verified` alert. Shown on the Opportunities card as "Applied -
verifying on next scan" until then. Verified live (negative path: a real
rescan correctly leaves an unresolved meta-description fix marked
"verifying" since the real page still lacks one) and via an automated test
covering the positive path with controlled HTML (fix resolves, opportunity
disappears, alert fires).

**Not yet built (explicitly deferred, not silently dropped):** actually
pushing a change to the user's live site (editing their WordPress/CMS/repo
directly) instead of the user applying it themselves. That needs a real
integration with wherever a given site's content lives, and the user had no
preference yet on which one to build first - revisit once a specific site's
hosting/CMS is known.

Also added as part of this phase: `POST /pages/{id}/keywords/action-plan` -
for a tracked keyword with no rank (or a poor one), an AI-generated action
plan (competitor gap analysis, same shallow SERP lookup as keyword
opportunities) for what would actually help *that* keyword start ranking,
as opposed to Phase C's "here are other keywords to try instead." Shown as
a 4th "Action plan" tab in `KeywordPanel`, only for keywords ranking #11+
or not found at all. Verified live with a nonsense keyword genuinely
producing a sensible, keyword-specific plan via real OpenAI.

## Phase E — Site Health rollup

**Status: done**

No external requirements — pure aggregation over data already stored (no
new tables, no API keys). `GET /sites/{id}/health` returns:
- **Score trend** — reconstructs what the site's blended score (same
  "average of each page's latest audit" the overview gauge already shows)
  would have read at every point in its audit history, not just right now.
  Charted with the same inline-SVG approach as the keyword rank-history
  chart (`ScoreTrendChart.tsx`).
- **Score wins/losses** — biggest per-page score deltas between each page's
  two most recent audits.
- **Keyword wins/losses** — biggest per-keyword rank deltas between the two
  most recent checks, including newly-found (win) and newly-lost (loss)
  transitions. This is new: until now the app only ever alerted on rank
  *drops* (`applied_fixes.py`/`scheduled_audits.py`) - improvements were
  never surfaced anywhere.
- `top_opportunities` (reused from Phase A, for API completeness) - the
  frontend doesn't re-render this since the existing `OpportunitiesPanel`
  already covers it on the same page.

Shown as a new "Site health" section on the site overview page, between the
score/stat summary and Opportunities. Verified live: trend chart correctly
reflects a real score change, wins/losses correctly categorize a keyword
improvement and a score drop with the right direction/delta, and the
existing Opportunities section stayed accurate alongside it.

## Phase F — Google Search Console / Analytics integration

**Status: code complete, unverified against real Google data**

Unlike every other integration so far, this is OAuth, not a static key:
Signal is registered as an app with Google, and each user grants access to
their own Search Console/Analytics data through a real Google consent
screen - there's no way to fully exercise it without a registered Google
Cloud OAuth client and a human completing that screen. Full setup steps in
`backend/README.md`.

Built: the OAuth connect/callback/status/disconnect flow
(`app/routers/google_integration.py`), encrypted token storage with
transparent refresh (`app/services/google_connection.py` +
`token_crypto.py`), GSC and GA4 API clients (`app/services/gsc.py`,
`ga.py`), a Settings page to connect Google and map each site to a Search
Console property + GA4 property, and per-page data: real search queries/
clicks/impressions/position, indexing status (the real answer to "page
ranks 0 because it's not indexed yet" - the original motivation for this
phase), and real traffic (sessions/pageviews/bounce/engagement). None of
it costs Signal credits, unlike SerpApi/OpenAI - a Google API call here is
free once the OAuth grant exists.

168 backend tests passing (mocked HTTP throughout, same pattern as
SerpApi/DataForSEO/OpenAI). What's verified live: the full "not connected"
UI, the clean error before `GOOGLE_CLIENT_ID` is configured, the Settings
property-picker UI, and the per-page panels' "Connect Google in Settings
first" error path. What's **not** verified live: an actual OAuth consent
round-trip and real GSC/GA API responses - that needs the Google Cloud
Console setup completed first.

**Not yet built on top of this:** requesting indexing for an unindexed
page (a real write action via a separate Indexing API + scope, deliberately
left out to keep the OAuth surface reviewable), and feeding GSC query data
into the Phase A opportunities list as a new opportunity type.

## Phase G — Public landing page

**Status: done**

`/` was previously the (auth-gated) dashboard home - there was no public
page to explain the product before signing up. The dashboard moved to
`/dashboard/*` (was a route group living at `/`; every internal link was
updated) and `/` is now a public marketing page (`frontend/app/landing-page.tsx`, rendered by `app/page.tsx`)
with login/register CTAs.

The page explains every shipped feature (Phases A-F) using stylized
recreations of the real dashboard UI - score gauge, check-card grid, rank
chart, opportunity states, site-health trend, GSC/GA stat rows and query
table - built from the product's own design tokens
(`frontend/app/globals.css`, `.lp-*` prefixed rules), not a generic
template. Keyword tracking/competition and Google Search Console/Analytics
get full-width "deep dive" treatment (competitor comparison, AI ranking
action plan, keyword opportunities with one-click add; impressions/clicks
trend chart) since those came up as the features to emphasize.

CTAs are auth-aware: logged out sees "Log in" / "Get started free"
(`/login`, `/login?mode=register`); logged in sees a single "Go to
dashboard" link instead, everywhere a CTA appears.

**Convention going forward:** the landing page is expected to track the
product, not drift from it - see the "Landing page parity" section in
`CLAUDE.md` for exactly what to update and when. Plan limits shown there
mirror `PLAN_LIMITS` in `backend/app/models.py`; Pro/Agency show "Contact us
to upgrade" (inert, not a link) rather than a real checkout, since Stripe
billing isn't built yet - see below.

## Not yet scheduled

- **Direct site-write integration** (WordPress/GitHub/etc.) — see Phase D.
- **Stripe billing** — deliberately deferred per earlier decision. The
  landing page's Pro/Agency plan cards are ready for a real checkout link
  once this exists.
- **Scheduled audits + alerts on Render** — the feature itself is built and
  works anywhere Celery+Redis run (see "Scheduled audits + alerts" in
  `backend/README.md`), but isn't provisioned on the production Render
  deployment (`render.yaml`, 2026-09-18 decision) — Render has no free tier
  for Background Workers or Cron Jobs, and right now Celery has exactly one
  consumer (the daily 3am beat job), so paying for it upfront wasn't worth
  it. Two ways to revisit once it is: (a) mirror the current code exactly —
  add a Celery worker + beat as two more Background Workers to `render.yaml`
  plus a Key Value (Redis) instance (free tier covers Redis, not the
  workers), or (b) replace Celery/Redis entirely with a single Render Cron
  Job calling `run_scheduled_audits` directly once a day — cheaper (billed
  per execution instead of two always-on dynos) but needs a small new CLI
  entrypoint script, since nothing else uses Celery today.
