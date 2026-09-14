# Signal — "one-stop SEO" roadmap

Goal: a user comes to Signal, sees exactly what's wrong with their site's SEO,
and can fix it (or improve keyword targeting) without leaving the app —
diagnosis and fix in one place, not just a report.

Today the app does diagnosis well (on-page audits, keyword rank tracking,
scheduled alerts) and fixes a *little* (AI rewrites for meta description and
title tag only). The gap is turning "here's a list of problems" into "here's
what to do next, and I can do it right here."

## Phase A — Unified "Opportunities" list

**Status: in progress**

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

Today `CheckList`'s suggestable checks are just `meta_description` and
`title_tag`. Extend `ai_suggestions.py` and the frontend's `SUGGESTABLE`
table to also generate: heading structure fixes, alt text,
readability/content rewrites, and internal-linking suggestions. Same
`AIProvider` abstraction, just more suggestion types — turns most audit
failures into a one-click fix instead of just two of them.

## Phase C — Keyword opportunity discovery

The headline "how do I improve keyword targeting" feature. Using the
competitor SERP data we already fetch (`get_competitors`) plus a page's own
content, ask the AI what keywords/topics the page is missing compared to
whoever outranks it, and let the user add a suggested keyword to tracking in
one click. This is what turns "you're not ranking" into "target this
instead."

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
