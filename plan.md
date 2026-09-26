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
`CLAUDE.md` for exactly what to update and when. The limits shown there come
from `ACCOUNT_LIMITS` in `backend/app/models.py` and the packs from
`GET /pricing`. (Historical note: this section originally described three plan
tiers with an inert "Contact us to upgrade" button; Phase I below replaced that
with credit packs and a real checkout.)

## Phase H — Admin panel (users, payments, credits)

**Status: built, tested and deployed (2026-09-19, commit `8f8d82f`); not yet run against a
real Dodo account.** Phase I below then replaced the subscription tiers with credit packs,
so some of the specifics here (plans, MRR, the plan-change endpoint) no longer exist.

**What was built** (all three phases plus the prerequisites):
- *Phase 0 - approval prerequisites:* `/terms`, `/privacy`, `/refunds` (drafts - the owner
  should review them, and the refund terms are the builder's defaults: 7 days on new plans and
  unused credit packs, 3 days on renewals), the support address `gharshit1237@gmail.com`
  (`SUPPORT_EMAIL`) in the footer and legal pages, and real prices on the landing Plans
  section. Per the owner's request, **pricing is configurable from the admin panel**
  (`/admin/pricing`, backed by the `Product` table and the public `GET /pricing`), with
  on-demand revalidation so edits show immediately. The Pro card and the "also included"
  strip no longer promise scheduled audits, which aren't running in production.
- *Phase 1:* migration `0008`, the credit ledger + atomic `apply_credit_delta` (fixing a real
  race: 12 parallel requests could spend a 3-credit balance), `ADMIN_EMAILS`/`require_admin`,
  `/admin` overview, users list and user detail with add/remove credits.
- *Phase 2:* payments ledger, manual payment recording, plan changes, revenue/MRR on the
  overview and user pages, audit log.
- *Phase 3:* Dodo checkout (`POST /billing/checkout`), signed `POST /webhooks/dodo` handling
  payments, subscriptions, refunds and disputes, customer portal, `/dashboard/billing`.
- Verification: 255 backend tests on real Postgres 16 (253 on SQLite; 2 are Postgres-only
  concurrency tests), migration up/down proven on Postgres from the 0007 state, webhook
  signing cross-checked against the reference `standardwebhooks` library, and the whole flow
  driven in a real browser against a mock Dodo (purchase, subscription, portal, expiry,
  refund).

**To go live** — superseded by Phase I's checklist below.

Goal: the owner can see who the users are, how much each has paid, and add
credits to any of them, without SQL against the production database.

**What existed before:** `User` had only `email`, `plan`, `credits_balance`,
`created_at` - no admin flag, no payment record of any kind (billing is
deferred, so "how much they paid" is $0 for everyone), and no credit history.
`deduct_credit` (`backend/app/services/credits.py`) is a Python
read-modify-write that logs nothing, so two concurrent requests can lose an
update and nothing records who spent what (REQUIREMENTS.md §3.3 already asks
for that log).

**Decisions made:**
- Amounts are in **USD** (2026-09-19), matching the draft pricing in
  REQUIREMENTS.md §3.2. One currency: totals are a plain sum, stored as integer
  cents (`amount_cents`), no `currency` column. If a second currency ever
  appears, add the column then (backfill `'usd'`).
- Payments are collected through **Dodo Payments** (chosen 2026-09-19), a
  Merchant of Record: no monthly/setup fee, 4% + 40¢ per sale (+1.5% for
  non-US cards, +0.5% for subscriptions), and Dodo collects/remits VAT, GST
  and sales tax on our behalf. Stripe direct is invite-only in India and
  Razorpay would leave global tax filing to us. Individuals (no registered
  company) can onboard. Chosen for the lowest per-sale MoR fee and India
  support; India payout details (INR vs USD, timing) are still to be confirmed
  during Dodo's sign-up.

**Defaults taken when building (the owner asked to build it all without changing them):**
- Admin = an email listed in an `ADMIN_EMAILS` env var, checked on every
  request by a `require_admin` dependency (403 otherwise). No DB flag, so no
  API can grant admin; revoking = editing the env. `/auth/me` returns a computed
  `is_admin` so the UI can show the link - the API is the real gate.
- Built inside this app (`/admin/*` API + Next.js pages), not an off-the-shelf
  tool like SQLAdmin (quick, but no ledger/payment workflow).

**Prerequisite for Dodo - done (see "What was built"); kept for reference.** Dodo only
approves an account (1-3 business days after submitting) once the live site
publicly shows: pricing with billing intervals, Terms of Service, Privacy
Policy, a refund/cancellation policy, and a monitored contact address, linked
from the footer. None of these exist on signal-seo.in yet. So "Phase 0" is:
- Add `/terms`, `/privacy`, `/refunds` pages (drafted from templates; the owner
  should review them - they're not legal advice) and a support address (e.g.
  forward `support@signal-seo.in` to the owner's inbox), linked from the landing
  footer.
- Put real prices on the landing Plans section (draft: Pro $24/mo, Agency
  $89/mo, 50-credit pack $9 - confirm before publishing). This is a landing
  page change, so the "Landing page parity" rule in `CLAUDE.md` applies.
- Owner signs up at Dodo (submitted 2026-09-19, verification in progress; government ID + selfie via Persona, bank details -
  the bank account name must match the verified identity) and submits the
  product form. Phases 1-2 can be built while Dodo reviews.

**Data model (migration 0008)** - plain string columns, *not* Postgres enums
(see the enum gotcha in `CLAUDE.md`):
- `credit_transaction`: `user_id`, `delta`, `balance_after`, `reason`
  (`signup`/`usage`/`admin`/`purchase`/`refund`), `ref` (e.g. `keyword_check`),
  `note`, `actor_id` (the admin, if any), `created_at`.
- `payment`: `user_id`, `amount_cents`, `kind`
  (`credit_pack`/`subscription`/`manual`/`refund`), `plan`, `credits_granted`,
  `provider` (`manual`/`dodo`), `provider_ref` (unique - webhook
  idempotency), `note`, `paid_at`.
- `admin_audit_log`: `actor_id`, `action`, `target_user_id`, `payload`,
  `created_at`.

**Credit service:** one `apply_credit_delta()` performs an atomic
`UPDATE ... SET credits_balance = credits_balance + :d` (with
`WHERE credits_balance >= cost` when spending) and inserts the ledger row in the
same transaction. `deduct_credit` becomes a wrapper; its ~dozen call sites
(keywords, suggestions) gain a `reason`. This fixes the race and produces the
usage log.

**Admin API (`/admin/*`, all `require_admin`):** stats (signups, revenue,
credits outstanding/spent); users list (search, filter by plan/paid, sort,
paginate); user detail (sites, payments, ledger, Google connected yes/no -
never tokens or password hashes, via explicit response schemas); `POST
credits {delta, note}` (note required, floor 0, capped); `POST plan`; `POST
payments` (manual; can grant credits/plan in the same transaction).

**UI:** `/admin` (summary), `/admin/users` (table), `/admin/users/[id]` (add
credits, record payment, change plan, ledger + payments tables). Reuses the app
shell and design tokens; `/admin` goes in `app/robots.ts`'s disallow list.
Internal-only, so no landing-page change.

**Phases:**
1. Users + credits: list, detail, add/remove credits, ledger, atomic spend.
2. Payments: manual recording, revenue on list/detail/stats, plan changes.
3. Real billing with Dodo (needs Dodo approval + test-mode products):
   - Owner creates the products in Dodo (Pro, Agency, 50-credit pack), test
     mode first, and pastes `DODO_API_KEY`, `DODO_WEBHOOK_KEY` and
     `DODO_ENVIRONMENT` (`test_mode`/`live_mode`) into Render; a small config
     maps each Dodo product id to `{kind, plan, credits}`.
   - `POST /billing/checkout {product}` (authenticated) creates a Dodo checkout
     session with the user's email and `metadata.user_id`, returns the hosted
     checkout URL; the frontend redirects there. Card data never touches Signal.
   - `POST /webhooks/dodo` (no login; authenticated only by the signature, via
     the official SDK's `webhooks.unwrap`, which implements the Standard
     Webhooks headers `webhook-id`/`webhook-timestamp`/`webhook-signature`).
     `payment.succeeded` calls `record_payment()` (idempotent on Dodo's payment
     id, since Dodo retries up to 8 times over ~10 hours) and grants the plan or
     credits; subscription-renewed/cancelled/expired and `payment.failed` move
     the plan; refund events add a refund row (and revoke credits if we decide
     to); dispute events flag the user. Return 2xx fast.
   - Credits stay in our own DB as the single source of truth - we sell packs as
     one-time products and grant on the webhook, rather than using Dodo's own
     credit-entitlement feature.
   - Store `dodo_customer_id` on the user and add `POST /billing/portal` so
     customers manage/cancel subscriptions and cards in Dodo's hosted portal.
   - Replace the "top-ups aren't available yet" 402 message in `credits.py` with
     a buy-credits link; make the landing Plans cards real checkout CTAs
     (landing parity rule); swap the unused `stripe_*` settings in `config.py`
     for the Dodo ones.
   - Optional: disable user (free signups get 10 credits per email, so throwaway
     accounts are cheap), CSV export, vendor-cost vs revenue.

**Open items to settle while building Phase 3** (not verified yet): the exact
subscription/refund event names (only `payment.succeeded`, `payment.failed` and
`subscription.active` were confirmed in Dodo's docs); which payload fields give
the customer charge vs tax vs our net settlement (decide what "paid" means in
the admin panel - gross charge excluding tax is the intent - by inspecting a
test-mode payload); INR vs USD payout and settlement timing for India.

**Still open:** optional extras (disable user, CSV export, vendor-cost vs revenue), scheduled
audits (see below), and the real-account verification above - in particular confirming that
checkout `metadata` reaches *renewal* payments (renewals are attributed by subscription id
either way), INR-vs-USD payout to India, and Dodo's exact tax/settlement fields on a real
payload.

**Tests written:** 401/403 for anonymous/non-admin, ledger sums to balance,
concurrent-spend test, payment idempotency on `provider_ref`, webhook rejected
on a bad signature, no `hashed_password` in any admin response, and a
real-Postgres migration run (throwaway `postgres:16`) since SQLite won't catch
enum/type mismatches.

## Phase I — Credit-only pricing + Google sign-in

**Status: built and tested (2026-09-19).** Two changes the owner asked for, plus a
database runbook.

**Pricing is now credits only.** The Pro ($24/mo) and Agency ($89/mo) subscriptions are
gone; there is one tier, the same limits for everyone, and the only thing for sale is a
one-time pack of credits. Why: everything that costs Signal real money (SerpApi rank
lookups, OpenAI calls) was already metered in credits, so tier gating was charging for
storage rather than for cost, and "free to use, pay for what you use" is a simpler promise
to keep. Nobody was subscribed, so nothing was lost.

- Migration `0009`: deletes the subscription products, adds `product.badge` and
  `payment.product_key`, and seeds a starter ladder (10 credits $2, 50 $5, 200 $15). It
  reprices the old `credits_50` row from $9 only if it is still exactly the value `0008`
  seeded — a price the owner has actually edited is left alone.
- `PLAN_LIMITS` → `ACCOUNT_LIMITS` (5 sites, 50 pages/site, 25 keywords/page, for
  everyone). The rescan throttle was "1/day for free, unlimited for paid", then 5 minutes
  for everyone, and is now **gone** — see "Rescans are not rate limited" below.
- `/admin/pricing` does full CRUD: create any number of packs, reprice, rename, badge,
  reorder (`POST /admin/products/reorder`, all ids at once so it can't half-apply),
  deactivate, delete. A pack that has **sold** can't be deleted, only deactivated — Dodo
  retries a webhook for ~10 hours and a delivery arriving after the row vanished would
  record the money and grant no credits.
- `payment.product_key` gives the overview a revenue-per-pack table, so the owner can see
  which price point actually sells.
- The `PlanTier` enum and `user.plan` column **stay** (they're unused, but dropping a value
  from a Postgres enum is exactly what broke production once; `payment.plan` still explains
  historical money). `/admin/users/{id}/plan` and `set_user_plan()` are gone. Subscription
  webhooks are logged to the audit trail and acknowledged rather than acted on — Signal
  sells nothing recurring, so one could only come from something set up in Dodo directly.

**Sign in with Google** is now the advertised way in (`/auth/google/start` →
`/auth/google/callback`). Email + password is kept as a deliberate fallback at
`/login?password=1`, so a misconfigured OAuth client can't lock the owner out of
production.

- Login asks for `openid email profile` **only**. Search Console/Analytics is a separate,
  later consent from Settings with its own redirect URI — signing up shouldn't look like
  handing over your whole Google account, and those three scopes are non-sensitive, so the
  consent screen needs no Google review to work for the public.
- CSRF: a nonce lives in both the signed `state` and an httpOnly cookie on the API's own
  origin; they must match, or a forged callback URL could sign a victim into the attacker's
  account.
- The Signal token comes back in the URL **fragment**, never the query string, so it stays
  out of access logs, proxies and the `Referer` header.
- Accounts match on *verified* email, so Google sign-in lands in an existing password
  account instead of silently creating a second one. An unverified Google email is refused.
- Google-created accounts store an empty password hash; `verify_password` returns False for
  an empty hash rather than raising, so no password can ever match one.

**`docs/DATABASE.md`** is the new runbook for creating, moving or rebuilding the database
from scratch, and for verifying the result (`alembic check` now passes clean — migration
`0010` fixed a pre-existing index/constraint drift on `googleconnection.user_id` that had
always made that check report a false difference).

**Verification:** 266 backend tests on real Postgres 16 (264 on SQLite; 2 are Postgres-only
concurrency tests), `alembic upgrade head` proven from empty *and* from a production-like
0008 database with users and a payment in it, both directions, plus the edited-price guard.

**Still the owner's to do, once Dodo approves the account:** create one **one-time** USD
product per pack in Dodo (test mode), add the webhook endpoint `/webhooks/dodo` with the
payment and refund events, set `DODO_API_KEY` / `DODO_WEBHOOK_KEY` / `DODO_ENVIRONMENT`,
paste the `pdt_…` ids into `/admin/pricing` and press "Check against Dodo", then make one
test-mode purchase before switching to `live_mode`. **And in Google Cloud Console:** add
`https://api.signal-seo.in/auth/google/callback` as a redirect URI on the OAuth client and
**publish the consent screen** — while it is in Testing, only listed test users can sign
in at all.

## Phase J — Crawling, keyword discovery, and search + AI visibility

**Status: built and tested (2026-09-20).** Three features aimed squarely at the gaps in
`docs/COMPETITORS.md`: no crawler, no keyword discovery, and nothing at all for AI search.

**1. Crawl a site instead of typing its pages in.** `POST /sites/{id}/crawl` finds pages
from the sitemap (robots.txt first, then /sitemap.xml), falling back to a shallow
breadth-first link walk when a sitemap yields almost nothing. robots.txt Disallow is
honoured either way. Free — Signal does the fetching itself.

- Query-string variants collapse to one page: a link to `/login?mode=register` is the
  same template as `/login`, and auditing both would spend two of the owner's fifty page
  slots on one page. Sitemap entries are exempt, since listing both means the owner meant
  both. utm/gclid-style tracking params are stripped outright.
- Sitemaps are parsed with a regex over `<loc>` rather than an XML parser: real sitemaps
  are routinely malformed, and a strict parse that throws returns nothing where a person
  can plainly see the URLs.

**2. Index status.** A page that isn't indexed cannot rank whatever its audit score says,
so the crawl checks each page against Search Console's URL Inspection API (free,
authoritative, and it gives Google's own wording for *why*). That needs the owner
connected *and* an owner of the property, which plenty of people aren't — so
`POST /pages/{id}/index-check` falls back to a `site:` lookup for 1 credit. Every row
records which source answered, because inference and Google-said-so deserve different
confidence.

**3. Keyword discovery.** `POST /sites/{id}/keywords/discover` merges three sources and
labels each idea with where it came from:
- **Search Console** — real impressions, clicks and position. Free. Sorted so near-misses
  come first: position 12 with 400 impressions is worth far more attention than position 2.
- **The page's own content** — an LLM reads the home page by default. 1 credit.
- **Google's related searches** — 1 credit.

Signal has **no search-volume database and does not pretend to have one**: only Search
Console ideas carry numbers, and the UI says so. Real volumes would come from DataForSEO's
Labs API, whose credentials slot already exists in config. The owner marks ideas as
targeted, which is both the input to a visibility run and the lever on what it costs.

**4. Search + AI visibility.** `POST /sites/{id}/visibility/check` asks, per targeted
keyword: does the domain rank in Google, does Google's AI Overview cite it, and does an
LLM name it when asked the keyword as a question? Google organic and the AI Overview come
out of *one* SerpApi response, so together they are one credit; the model question is a
second. 2 credits per keyword.

- "Google showed no AI Overview" and "it showed one and picked someone else" are
  different results and are reported differently — the second names who won instead,
  which is the actionable half.
- The ChatGPT reading is honest about what it is: the completion API answers from what the
  model already knows, so it measures whether a brand is in the model's picture of a topic.
  It is not a claim about what live browsing would cite, and the UI says that rather than
  letting the number imply more than it means.
- Brand matching deliberately won't match the first word of a hyphenated name — otherwise
  a site called signal-seo.in matches every sentence containing "signal".

**Background jobs.** All three run through `app/services/site_jobs.py` on FastAPI's
`BackgroundTasks`, not a worker queue: Render's free tier has no worker and a monthly bill
isn't worth it pre-revenue (the decision from Phase H stands). The consequences are
handled explicitly — own session, commit-as-you-go, stale-job detection, credits spent one
unit at a time — and are written up in `CLAUDE.md`. If a worker is ever provisioned only
`site_jobs.start` changes.

**Verification:** 317 backend tests on real Postgres 16, migration `0011` proven up and
down with `alembic check` clean, and the crawler run against the real signal-seo.in (which
is how the `/login?mode=register` duplicate was found and fixed).

**The site page now leads with it.** `SearchPresencePanel` replaced the opportunities list
in the prime slot: two gauges (Google, AI answers) that sweep up from zero on mount, and
the home page's Search Console impressions as a self-drawing area chart with a hover
readout. Opportunities moved below the pages they refer to rather than being removed - it
is still the list the product is about. Everything the panel shows is derived from data
already stored, so opening a site costs nothing.

One bug worth remembering came out of looking at the chart: Search Console reports about
two days behind, and drawing those trailing zeros plunged the line to the floor - it read
as traffic collapsing, and it dragged the week-on-week figures from +31% down to +2%.
Trailing zeros inside the lag window are trimmed; a genuine run of quiet days is not, and
is still drawn.

**A silent-data bug found by a user question.** The site page showed no Search Console
impressions while the page below it showed Analytics pageviews, which looked like a
contradiction. It wasn't - the site was days old, indexed but ranking for nothing, and the
pageviews were direct visits - but checking it exposed a real fault behind it. Search
Console matches a page by *exact URL*, and the crawler was stripping trailing slashes. For
any site whose canonical URLs end in `/` (WordPress and friends) Signal would have stored
a URL Google has never heard of, and every search query for that page would have come back
empty, looking exactly like a page with no traffic. Fixed three ways: the crawler now
preserves the site's own slash (de-duplicating on a slash-insensitive key instead),
hand-typed URLs are normalised on entry without touching the path, and the Search Console
lookup retries the other slash form before reporting nothing - which is what rescues rows
stored before the fix. Google Analytics never had the problem because it matches on
`pagePath`; that asymmetry is what made the two panels disagree.

**Free signup allowance raised 3 → 10 (2026-09-20).** A growth lever with a direct cost:
every credit is a real SerpApi or OpenAI call, and there is still nothing stopping a
throwaway email from collecting another ten (see the disable-user note above - that is the
obvious mitigation when it starts mattering). The number lives in one place,
`SIGNUP_CREDITS` in `models.py`, and is read late rather than copied at import so changing
it changes every reader at once. The test suite pins it to its own value, because dozens
of assertions about credit arithmetic were tracking a product decision they had no
interest in; the tests that genuinely care assert against the constant itself.

**Per-keyword advice (2026-09-20).** The visibility table answers "am I visible"; this
answers "what do I do about it". Every suggestion is built from measurements Signal
already has for that exact search: the pages outranking the site with their titles, the
sources Google's AI Overview cited and what its answer actually said, what an assistant
answered instead, and the content of the site's own most relevant page. The model is given
that and nothing else, and is told explicitly that "improve content quality" and "build
backlinks" are not acceptable answers - grounding is the entire difference between this
and filler. Each action says whether it addresses ranking, AI citation, or both, since
those are different problems.

The evidence is captured into `visibilitycheck.context` during the check, which had
already fetched it and was throwing it away. That makes advice one credit rather than two,
and - more importantly - makes it advice about the search actually on screen rather than a
fresh one that may differ. Advice is stored so re-reading is free, and stamped with the
reading it came from so the UI can flag it once the keyword is re-checked.

**Paying once per result (2026-09-20).** Nine things a credit buys - the six AI suggestions
on a page audit, plus competitors, keyword opportunities and the action plan - existed only
in React state. Refreshing the page threw them away, and the only way back was to pay
again. They are now written to `generatedresult` in the same transaction as the credit that
paid for them (one row per page + kind + subject, upserted, so regenerating replaces rather
than accumulates), and every page seeds itself from `GET /pages/{id}/generated` on mount.
Reading back costs nothing. Session-generated values win over stored ones while a tab is
open, so a regenerate is never overwritten by the restore.

Two smaller things landed with it. A keyword can be typed in by hand on the visibility page
(`POST /sites/{id}/keywords`, `source="manual"`, targeted immediately) rather than only
arriving via discovery - the empty state was otherwise a dead end for anyone who already
knows what they want to rank for. And the credit balance in the sidebar now updates without
a reload: `api.request()` takes a `metered` flag, fires a listener on success only (a 402 or
a vendor failure charged nothing), and `auth-context` refetches the user. That exposed a
real bug in `useSiteJobs` - the "don't fire for jobs that already existed when the page
opened" guard was keyed per job kind, so a site's *first* run of a kind that finished
before the next poll looked pre-existing and never refreshed anything. The baseline is now
taken once per site, on the first poll.

**Eating our own output (2026-09-20).** Signal's visibility check said the site doesn't
rank for "auto seo" and isn't cited by the AI Overview, and its own advice endpoint gave
the reason: no page here is about automated SEO tools, while every page that does rank is.
So `/auto-seo-tools` exists — a long-form page covering what the category automates, the
audit checklist item by item, what Signal does, and what it can't do. It is the first real
test of whether the advice feature produces work worth doing.

Three of the suggestions were followed and one was not. Followed: a dedicated page, a
numbered checklist (the AI Overview's sources all had one), and explicit coverage of the
features the Overview named — keyword tracking and technical fixes. Not followed: user
reviews. Signal has no users to quote, and inventing testimonials is the one thing on that
list that would have been faster to write than anything else and worth less than nothing.
Link building got a section saying Signal deliberately doesn't do it, which is the honest
version of "cover the features the Overview mentions".

**Keeping a plan, and checking one keyword (2026-09-20).** Two complaints about the
visibility page, both about the same thing: money.

The advice was already stored and already free to re-read, but the page hid that. After a
reload the row said "How to improve" — the exact label on the button that spends a credit —
and the plan was collapsed behind it, so a plan that had been paid for looked like one that
hadn't. Now: "View plan" in the accent colour when one exists, "Get a plan" when one
doesn't, the open rows are remembered per browser, and the staleness note says the plan
stays until it's replaced rather than asking for a fresh one. Nothing about the storage
changed, because nothing about it was broken — it was legible to the database and not to
the person paying.

The second: checking visibility was all-or-nothing, so asking "did this one keyword move?"
cost 2 credits per keyword on the site. `POST /sites/{id}/visibility/check` now takes an
optional keyword, and each row has its own check. The body stays optional so the "Check
all" button is the same call it always was.

**Off Netlify, onto Render's CDN (2026-09-20).** Netlify's free plan is 300 credits a
month and a production deploy costs 15 of them — about twenty deploys — with bandwidth at
20 credits/GB. Over the limit the site is *paused* until the next billing cycle, along
with every other project on the account. Not a bill to negotiate: an outage, on the
public pages, days after starting to care about ranking.

Render's static sites are free and never sleep. Its free *web services* do sleep — 15
minutes idle, ~a minute to wake — which is why the frontend is a static export rather
than a Node service: a one-minute first byte for Googlebot would have undone the
`/auto-seo-tools` work.

The export costs three things, all of which turned out to be cheap. Dynamic route
segments can only be pre-rendered if they can be enumerated, and per-user ids can't, so
dashboard ids moved into the query string (`lib/routes.ts` owns every URL now, which is
better than the 24 hand-built template literals it replaced). Old links are rewritten to
`/legacy-link`, which reads the path the rewrite preserved and forwards. And the landing
page's 5-minute ISR became a build-time fetch plus a deploy hook the *API* fires after a
pricing change — on the API because a deploy hook spends build minutes, and anything the
browser can send is public.

Nothing was lost that the SEO pages care about: `/` and `/auto-seo-tools` were already
prerendered, and now they come off a CDN with no origin to wake up.

**Rescans are not rate limited (2026-09-20).** "Run full scan" was reporting "4 page(s)
could not be rescanned (rate limit or fetch error)". The rate limit was ours: a five-minute
minimum gap per page, left over from when a daily rescan was the free tier's upgrade nudge.
It is gone. Audits cost no credits — Signal fetches the page itself — so the limit was
protecting nothing the owner was paying for, and it broke the one thing the button is for:
edit a page, come back, check whether the failure cleared. It also broke "Run full scan"
against itself, since that walks every page in turn and collided with its own previous run.

What a gap really guards against — hammering someone's web server — is a fetch concern and
stays with the fetch: one request per page, a timeout, a bot user agent.

The message was the other half of the bug. It counted failures and guessed at the cause,
naming the one thing it could no longer be, and never said *which* page. It now lists each
failed page with the reason the server gave ("/pricing — Could not fetch page: Client error
'404 Not Found'"), trimmed to the first line because httpx appends an MDN link.

**The API no longer sleeps (2026-09-22).** "Continue with Google" was landing people on
Render's "service waking up" page: the free plan sleeps a web service after 15 idle
minutes and takes about a minute to wake. There was already a GitHub Actions workflow
pinging it every ten minutes, and the API slept anyway. Its run history showed why:
GitHub runs scheduled workflows best-effort, and it had run a `*/10` schedule 29 times in
four days — median gap 173 minutes, every gap longer than the fifteen that matter. No
schedule on GitHub could have fixed this.

So the API pings itself: a task in the lifespan requests the service's own public URL every
ten minutes, which leaves the instance and comes back through Render's proxy as inbound
traffic. It is keyed off `RENDER_EXTERNAL_URL`, so it needs no configuration in production
and never runs in dev or tests. The workflow stays, recast as a backstop — it is the only
thing outside the process that can wake the service if the loop ever dies with it.

Free, with one condition. Render grants 750 free instance-hours per workspace per month;
always-on uses up to 744; exhausting the pool suspends *every* free service until the 1st.
Three of the owner's older free services shared that pool and were suspended so the API
can be the only one drawing on it. That constraint is now written into CLAUDE.md, because
resuming any of them quietly re-creates the risk.

Found on the way: `auth-context` deleted the session token whenever `/auth/me` failed for
*any* reason, so a sleeping API signed everyone out. Only a 401 does that now.

**Billing switched on (2026-09-25).** The Dodo account passed verification, so the
integration built in Phase I finally has something to talk to. No code was needed - the
client, the hosted checkout, Standard Webhooks verification and the credit ledger were all
written and tested months earlier. Re-checked against Dodo's current API docs before
trusting it with money: `POST /checkouts`, every field the client sends, and the three
`webhook-*` signing headers are all still current.

What it took was configuration: three one-time USD products in live mode (tax category
SaaS), their `pdt_…` ids saved against the packs in `/admin/pricing`, and the existing
webhook endpoint extended to the dispute events the handler already implements alongside
payment and refund. The two secrets - the API key and the webhook signing secret - are the
owner's to paste into Render, which is also what flips `billing_enabled`.

One thing worth knowing about the money: Dodo adds tax **on top** of the listed price, so a
$2 pack charges $2.20 where tax is 10%. The webhook already subtracts it before recording
`amount_cents`, and credits come from the `Product` row rather than the amount paid, so a
customer in a high-VAT country still gets exactly what the pack says.

Switching it on surfaced a bug that had been waiting since the static-export move. The API
said `billing_enabled: true` and all three packs `purchasable: true`, but the public
pricing page still said "Coming soon" after a green rebuild. Next caches build-time fetches
by URL in `.next/cache`, Render restores that cache between builds, so the rebuild served
the *previous* build's `/pricing`. Clearing the build cache fixed the live page; the
landing page now appends `?build=<timestamp>` so it can't happen again. The obvious fix,
`cache: "no-store"`, was tried and rejected: under `output: "export"` it turns the route
dynamic and the export emits no `index.html` at all - caught by checking the build output
rather than trusting "Compiled successfully".

**Postgres moved to Aiven (2026-09-26).** Render's free Postgres is deleted 30 days after
it is created, and this one was dated 18 October - a deadline, not a preference. It now
runs on Aiven's free tier: PostgreSQL 18, DigitalOcean Bangalore.

The schema went over by running the migrations, not by restoring a dump: all 14 ran
unchanged on PostgreSQL 18 against a source on 16, and `alembic check` came back clean.
The data went table by table in foreign-key order, with every identity sequence reset
afterwards - the step a naive data-only dump skips, and the one that would otherwise make
the very next insert collide with row 1. Verified three ways: per-table row counts on both
sides (375 rows, every table matching), the credit invariant still holding on the copy
(each balance equal to the sum of its ledger), and an insert rolled back to prove the
sequences.

The interesting constraint is connections. The free plan allows 20 and Aiven's own agents
hold about 13, leaving roughly 7 for Signal, while SQLAlchemy's default pool is 5 + 10 per
process. That would have exhausted the plan under mild concurrency - including the
`alembic upgrade head` that runs on every deploy - so the pool is pinned to 2 + 3.
`pool_pre_ping` went on at the same time: the API is in Singapore and the database is now
in Bangalore, so idle connections get dropped between requests and without a pre-ping the
first query after a quiet spell fails in front of a user.

**Not built, deliberately:** search volumes, backlinks, and anything needing a crawled
index. See `docs/COMPETITORS.md` — those are index plays that cost more than this product
will earn for years.

## Phase K — Apply the fix, not just suggest it

**Status: planned**

The goal stated at the top of this file — "diagnosis and fix in one place" — is
still only half met. Every surface that finds a problem now also writes the fix
text, and the user copies it somewhere by hand. Phase K removes the copying.

The thing to be clear-eyed about: **the missing piece is not AI.** Signal
already generates the replacement title, the meta description, the heading
outline, the alt text, the per-keyword action plan and the visibility advice.
Four separate things are missing, and only one of them is a model call:

1. **A precise change instead of prose.** `visibility_advice` emits
   `{title, detail, addresses}` written for a human to read. "Answer the
   question in the first paragraph, like the pages that outrank you" is not
   something software can apply. A change has to name a page, a field, the
   value that is there now, and the value to put there.
2. **A way to write it.** Signal has no write access to anyone's site. This is
   the actual product work in this phase.
3. **Undo.** A write to someone's live site that can't be reversed in one click
   is not shippable.
4. **Verification** — already built. `applied_fixes.verify_applied_fixes_for_*`
   closes the loop on the next audit or rank check and raises `fix_verified`.
   Auto-applied changes go through `mark_applied()` so this machinery is reused
   unchanged rather than reimplemented.

### Sequence (decided 2026-09-26)

K1 → K2 (WordPress) → K3 (GitHub) → K4 → K5. The two write channels are built
back to back, on purpose: an interface with one implementation is indistinguishable
from that implementation, and WordPress (a remote API, writes land instantly, undo
is another write) and GitHub (a repo, writes land as a reviewable PR, undo is
closing it) are different enough to find a wrong abstraction while it is still
cheap to move. The `manual` target ships in K1 and never goes away — it is what
every unconnected site gets.

What K1 touches, concretely:

- `alembic/0015_*` — `SiteWriteTarget`, `ProposedChange`. `alembic check` clean;
  run the suite against real Postgres (`TEST_DATABASE_URL=...`) before merging,
  since this is a schema change.
- `app/services/changes.py` (new) — the compiler. One function per field, each
  returning a `ProposedChange` or `None`. Deterministic fields (`canonical_tag`,
  `robots_meta_tag`) resolve without a model; the rest reuse the existing
  `ai_suggestions` functions and add the `before` value read from the page's real
  HTML via `fetcher.fetch_html`.
- `app/services/write_targets/` (new package) — `base.py` with the four-method
  interface (`test`, `read`, `write`, `revert`) and `manual.py`, the only
  implementation in K1. Same shape as `ai_providers`/`rank_providers`, except
  the choice is per *site*, not per config: each site lives somewhere different.
- `app/routers/changes.py` (new) — compile, list, revert. Ownership through
  `get_owned_page`, like every other page-scoped route.
- `app/services/applied_fixes.py` — `mark_applied()` called on apply, so the
  existing verify loop picks auto-applied changes up with no new code.
- `frontend/lib/api.ts` — new methods, `metered: true` on the compile one.
- `frontend/components/CheckList.tsx` — the six `SUGGESTABLE` entries gain a
  diff view; `canonical_tag`, `robots_meta_tag` and `structured_data` gain their
  first buttons.
- `frontend/components/OpportunitiesPanel.tsx`, `KeywordPanel.tsx`, and the
  visibility page — the same diff component, wherever a suggestion already appears.
- `CREDIT_COSTS` in `landing-page.tsx` **and** the "What a credit buys" panel on
  `/dashboard/billing` — one edit is a lie on the other page.

### K1 — The change model and the compiler

**No writing at all**, no credentials, works for every site, and worth shipping
on its own: today the user is told "add a meta description"; afterwards they are
shown the exact before and after.

A new `ProposedChange` row is the unit of work: which page, which field, the
value read off the live page at compile time (`before`), the value to set
(`after`), where the suggestion came from, and a status. It is also the durable
record of a paid result — see "Credits" below.

Every suggestion in the app sorts into exactly three buckets, and the split is
the important part of this phase:

- **Deterministic — no model runs, no credit charged.** `canonical_tag` (the
  page's own normalised URL) and `robots_meta_tag` (drop the directive that is
  blocking indexing). Both are computable with certainty. Note that these two,
  plus `structured_data`, are the *most* mechanically fixable checks in the
  audit and are currently the ones with **no** AI generator and no button at
  all — `SUGGESTABLE` in `CheckList.tsx` covers the other six. The cheapest
  wins in this phase are the checks that were skipped.
- **Model-compiled, one bounded value.** Title, meta description, H1, alt text
  per image, a JSON-LD block, an internal link with its anchor and insertion
  point. Reviewable at a glance and reversible exactly.
- **Not applicable, and never given an Apply button.** "Publish a comparison
  page", "get cited by the sources the AI Overview used", "earn links". These
  produce a draft and say plainly that a person has to do the rest. A button
  that cannot do anything is the same failure as a landing-page claim the
  product doesn't back.

The compiler is a new service that takes one suggestion plus the page's real
HTML and returns a `ProposedChange` **or declines**. Declining is a first-class
outcome: an action that won't compile is shown as advice, exactly as today.

### K2 — WordPress

Chosen first if the audience is other people's sites: it is a third of the web
and the one CMS with a write API that is already there.

Application Passwords (WP 5.6+, per-user, revocable from the WP profile screen,
no plugin to install), Basic auth over HTTPS only, stored encrypted with the
existing `token_crypto` — same reasoning as `GoogleConnection`, since a leaked
app password is standing write access to the user's site.

**Spike this before committing to it.** `title` and `excerpt` are core REST
fields and will write cleanly. **The meta description is not core** — it belongs
to Yoast (`_yoast_wpseo_metadesc`) or Rank Math (`rank_math_description`), and
whether it is writable over REST depends on the plugin and its version. If a
test against a real WordPress shows it isn't, there are two honest answers: a
small Signal companion plugin that registers those fields (one more install
step for the user), or a WordPress path that only claims the fields core
exposes. Do not put "we set your meta description" in the UI before that test
passes. Resolving a page URL to a post id also needs `?slug=` or `wp/v2/search`
rather than a guess.

### K3 — GitHub

The right path for a code-built site (and the only one that fits Signal's own
`signal-seo.in`, a Next.js static export in a repo).

**A pull request, never a push to the default branch.** Review before merge is
what makes writing to a codebase acceptable at all, and it costs nothing to
offer.

Mapping a URL to the source file that produces it is the hard part — Next.js,
Hugo, Jekyll and Astro all answer it differently. The trick that avoids
encoding any of those conventions: search the repo for the **exact current
value** Signal just read off the live page. A title string is close to unique
and pins the file and the line. Zero matches or several means ask, not guess.

### K4 — Fix everything

A bulk apply as a `SiteJob` (`kind="apply"`), polled by the existing
`useSiteJobs` — background jobs run in the API process, so it needs its own
session from `session_factory()` and must commit progress as it goes, like
every other job here.

Every change is listed with its diff *before* anything runs. The default is
review-then-apply. "Apply all without looking" is not the default even once the
undo works, because the undo is per change and a surprise is still a surprise.

### K5 — Content-level changes

New sections and new pages, as **drafts a person places**. Rewriting someone's
body copy automatically is a different risk class from setting a meta tag: the
failure mode is not a wrong tag, it is a page that no longer says what the
business meant. Signal drafts it and stops.

### Gates

- **Verified sites only.** `Site.verified` must be true before a write target
  can be attached. Writing to a domain the account hasn't proven it owns is the
  one mistake in this feature that cannot be walked back.
- **`before` is captured before every write**, so revert is a one-click,
  free, exact restore of what was there.
- **A stale change is refused, not applied.** If the live value no longer
  matches `before`, someone edited the page after the change was compiled;
  overwriting them silently is worse than asking. Same reasoning as the `stale`
  flag on `VisibilityAdvice`.

### Not built, deliberately

**A JavaScript snippet that rewrites title/meta in the browser.** It is the
easiest possible write path and it would undermine the product's own pitch: AI
assistants and most non-Google crawlers don't run JS, so the fix would be
invisible in exactly the places Signal measures visibility — and swapping
indexed content client-side is cloaking-adjacent. Rejected on the merits, not
overlooked.

### Credits

One credit per **compiled change** — that is the model call. **Applying is free
and reverting is free.** Charging to press the button the whole feature exists
for would make people hesitate over it, and charging for undo is indefensible.
Deterministic changes (canonical, robots) cost nothing because no model runs.

Per `CLAUDE.md` that means editing `CREDIT_COSTS` in `landing-page.tsx` *and*
the "What a credit buys" panel on `/dashboard/billing`, and `metered: true` on
the `lib/api.ts` method so the sidebar's credit count drops without a reload.

`ProposedChange` is the stored result rather than a `generated_results.store()`
row, which is a deliberate exception to the rule in `CLAUDE.md`. The rule exists
so a refresh never loses what a credit bought; a durable row with a lifecycle
(applied, reverted, stale) satisfies that better than a table whose contract is
"newest replaces, no history". Applying and reverting are history and must not
be overwritten.

### Schema

Migration 0015, two tables: `SiteWriteTarget` (one per site — kind, config JSON,
encrypted secret, status, last checked) and `ProposedChange` (site, page,
origin, field, before, after, status, receipt, applied/reverted timestamps,
error). Plain string columns for kind/status/field, **not** Postgres enums — see
the block comment above `Product` in `models.py`; a label mismatch between a
Python enum name and a Postgres enum label once silently broke every audit in
production. `alembic check` stays clean, and the suite runs against real
Postgres before this ships.

### Landing-page and `/auto-seo-tools` parity

This phase falsifies two claims that are currently load-bearing, and they have
to change in the same commit as K2:

- `/auto-seo-tools`, "What auto SEO tools can't automate" → "**Changing your
  website.** … Nothing connects to your CMS and nothing edits your pages."
- `content.ts`, "Can SEO be fully automated?" → "Signal reports and suggests, it
  does not edit your website for you."

The replacement is a *narrower* claim, not a bigger one: Signal writes the
mechanical fields to a connected CMS, with a one-click undo, on sites the owner
has verified — and still does not decide what to publish, and still earns no
links. That stays true, and the section keeps doing the job it exists for.

## Not yet scheduled

- **Direct site-write integration** (WordPress/GitHub/etc.) — now planned as Phase K
  above; Phase D is the manual half of it.
- **Real keyword search volumes** — would come from DataForSEO's Labs API (its credential
  slots already exist in config). Deliberately deferred: it costs per lookup, and labelled
  ideas without volumes are more honest than invented estimates. See Phase J.
- **Scheduled audits + alerts on Render** (also: the landing page no longer advertises them
  - re-add "daily scheduled audits" to the "also included" strip once this is provisioned;
  `run_scheduled_audits` now covers every account, since there are no tiers to gate it on) —
  the feature itself is built and
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
