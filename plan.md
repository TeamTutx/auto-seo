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
  everyone). The rescan throttle was "1/day for free, unlimited for paid"; with no tiers
  it is 5 minutes for everyone, short enough for the apply-a-fix-then-verify loop.
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

**Not built, deliberately:** search volumes, backlinks, and anything needing a crawled
index. See `docs/COMPETITORS.md` — those are index plays that cost more than this product
will earn for years.

## Not yet scheduled

- **Direct site-write integration** (WordPress/GitHub/etc.) — see Phase D.
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
