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

Let a user mark a recommendation as "applied," then have the next scheduled
audit/rank-check automatically confirm whether it worked (score up, rank
improved) instead of relying on the user to notice. Builds on the existing
scheduled-audits/alerts system.

## Phase E — Site Health rollup

A single per-site dashboard: score trend over time (we already keep every
historical `Audit`, same charting approach as the rank-history chart),
biggest wins/losses, and the top items from Phase A's opportunity list — the
actual "come here and see everything" home screen for a site.

## Not yet scheduled

- **GSC/GA integration** — real traffic and real search-query data instead
  of only SERP-checked keywords would make Phase C much stronger, but it's
  blocked on setting up Google OAuth credentials. Sequence after the above.
- **Stripe billing** — deliberately deferred per earlier decision.
