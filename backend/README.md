# Signal backend

FastAPI service covering steps 1-4, 6, and most of 7 of the build order in
[`../docs/REQUIREMENTS.md`](../docs/REQUIREMENTS.md#8-suggested-build-order),
plus site verification (§2.1) and competitor comparison (§2.4). Step 5
(Stripe) is deliberately skipped for now — see "Known gaps" below.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Local dev defaults to SQLite (zero setup). Point `DATABASE_URL` in `.env` at
Postgres for anything beyond local dev.

## Run

```bash
uvicorn app.main:app --reload
```

Tables are created automatically on startup for the SQLite dev path. For
Postgres, run migrations instead:

```bash
alembic upgrade head
```

For scheduled audits (see below), you also need Redis plus a Celery worker
and beat process:

```bash
redis-server                                          # or: brew services start redis
celery -A app.workers.celery_app worker --loglevel=info
celery -A app.workers.celery_app beat --loglevel=info
```

## Test

```bash
pytest
```

`app/services/audit_engine.py`, `app/services/ai_suggestions.py`,
`app/services/scheduled_audits.py`, and both `app/services/rank_providers/*`
implementations have pure/near-pure unit tests (no DB/network - HTML or a
fixture response in, findings/prompt/alerts out). The `*_api.py` test files
exercise full request flows through FastAPI's `TestClient` against an
in-memory SQLite DB (shared fixtures in `tests/conftest.py`), with every
external vendor call (`get_rank_provider()`, `get_ai_provider()`,
`audit_page`, DNS/HTTP lookups) monkeypatched so no test ever hits a real
vendor or costs real money.

## What's here

- `app/models.py` — SQLModel schema: `User`, `Site`, `Page`, `Audit`,
  `Check`, `KeywordRank`, `Alert`, plus `PLAN_LIMITS` for free/pro/agency
  gating.
- `app/routers/` — `auth` (register/login/me, JWT), `sites`, `pages`,
  `audits`, `keywords`, `suggestions`, `alerts`. Plan limits (§3.1), the
  free-tier 1x/day rescan throttle, and per-check credit spend are enforced
  in the routers. `sites`/`pages` also have `PATCH`/`DELETE`; deleting
  either cascades through `app/services/cascade_delete.py` (no ORM-level
  cascade configured, so this is done manually - audits/checks/keyword_ranks
  would otherwise be orphaned).
- `app/services/credits.py` — the shared credit-spend gate
  (`require_credits`/`deduct_credit`) used by `keywords`, `suggestions`,
  and the competitor-lookup endpoint, so metered features can't drift out
  of sync with each other.
- `app/services/audit_engine.py` — the on-page audit checks from §2.2
  (title, meta description, headings, alt text, links, content length,
  keyword density, readability, canonical, robots meta, structured data).
- `app/services/audit_runner.py` — fetches a page's HTML and persists an
  `Audit` + its `Check` rows; called from the audits router, the scheduled-
  audit task, and (indirectly) the competitor/rank-check services.
- `app/services/site_verification.py` — domain ownership verification
  (§2.1): DNS TXT, meta tag, or a hosted file, same three options Google
  Search Console offers. Each check returns `(verified, message)` instead
  of raising, since "not verified yet" is a normal outcome, not an error.
- `app/services/rank_providers/` — rank-data vendor integrations (§2.4, §7),
  behind one interface so swapping vendors doesn't touch calling code:
  - `base.py` — the `RankProvider` ABC. The one abstract method is
    `fetch_serp` (returns the full parsed SERP as `List[SerpResult]`);
    `fetch_rank` is a concrete method built on top of it (finds one domain
    in that list). This is what lets competitor comparison exist with zero
    new vendor-specific code — it's the same SERP fetch, minus your own
    domain.
  - `dataforseo.py`, `serpapi.py` — one class per vendor, each split into
    the actual HTTP call (needs real credentials, untested here since it
    costs real money per request) and a `parse_serp` static method (pure
    response parsing, unit tested against fixture JSON).
  - `__init__.py` — `get_rank_provider()` reads `RANK_PROVIDER` from config
    and returns the matching instance; this is the only thing the rest of
    the app calls. **To add a vendor**: subclass `RankProvider`, register it
    in `_PROVIDERS`, add its credentials to `config.py`/`.env`. **To switch
    the active one**: change `RANK_PROVIDER` in `.env` — nothing else.
- `app/services/keyword_rank_runner.py` — persists one rank check
  (`KeywordRank` row) for a page, tagged with whichever provider ran it, so
  historical rows stay accurate even after switching vendors later.
- `app/services/competitors.py` — top organic results for a keyword,
  excluding the page's own domain (§2.4); a thin filter over the same
  `fetch_serp` call the rank checks use.
- `app/services/ai_providers/` — AI-vendor integrations (§2.2, §2.7), same
  pattern as `rank_providers/`:
  - `base.py` — the `AIProvider` ABC with one generic method, `complete`,
    rather than a method per suggestion type (so content briefs etc. can
    reuse it without touching this package).
  - `openai.py`, `anthropic.py` — one class per vendor.
  - `__init__.py` — `get_ai_provider()` reads `AI_PROVIDER` from config.
    **To switch vendors**: change that env var — nothing else.
- `app/services/ai_suggestions.py` — `generate_meta_description` and
  `generate_title_tag` each build a prompt (page title/keyword/content
  snippet in, suggested text out) and call `get_ai_provider().complete(...)`;
  this is where a new suggestion type (content briefs, §2.7 v2) would go.
- `app/services/scheduled_audits.py` — re-audits every Pro/Agency page and
  raises an in-app `Alert` on a meaningful regression (score drop ≥10
  points, or a check that newly started failing). See "Scheduled audits +
  alerts" below.
- `app/workers/` — Celery app. `run_page_audit` wraps a single on-demand
  audit but isn't wired into the API yet (audits still run inline - see
  `app/routers/audits.py`). `run_scheduled_audits` **is** live: it's what
  Celery Beat's daily schedule (`celery_app.py`) actually calls.
- `alembic/` — hand-written migrations (no live Postgres to autogenerate
  against yet); regenerate if they drift from `models.py`.
- `app/services/google_oauth.py` — pure-HTTP OAuth 2.0 (authorize URL,
  code exchange, refresh) - no DB access, so it's fully testable without a
  database. `app/services/google_connection.py` is the DB-backed layer on
  top (`GoogleConnection` row per user, encrypted tokens via
  `app/services/token_crypto.py`, transparent refresh-on-expiry).
- `app/services/gsc.py`, `app/services/ga.py` — Search Console and
  Analytics (GA4) API clients, same "one class, pure HTTP, parse the
  vendor's response shape" pattern as `rank_providers/`/`ai_providers/`.
- `app/routers/google_integration.py` (connect/callback/status/disconnect)
  and `app/routers/google_data.py` (per-page queries/index-status/metrics)
  — see "Google Search Console / Analytics integration" below.

## Site verification (§2.1)

- `POST /sites/{site_id}/verify` — body `{"method": "dns_txt" | "meta_tag" | "file_upload"}`.
  Checks the corresponding real DNS record / page meta tag / hosted file
  against the site's `verification_token` (auto-generated on creation) and
  sets `Site.verified = true` on success. Changing a site's domain
  (`PATCH /sites/{id}`) resets `verified` to `false` - a new domain hasn't
  been proven yet.
- Not credit-gated: DNS lookups and our own HTTP fetches don't cost real
  money the way a rank-provider or AI-provider call does.

## Keyword rank tracking (step 6) + competitor comparison (§2.4)

- `POST /pages/{page_id}/keywords` — track a keyword and run its first
  check. New keyword strings count against the plan's
  `max_keywords_per_page` (free: 3); rechecking an already-tracked keyword
  doesn't. Every check (new or recheck) spends 1 credit from
  `User.credits_balance` regardless of plan — see "Why every check spends
  a credit" below. Defaults to India (`location_code=2356`, see "Default
  search location" below); pass `location_code`/`language_code`/`device`
  explicitly to override (the frontend's `KeywordPanel` now exposes a
  location/device picker on the add-keyword form).
- `GET /pages/{page_id}/keywords` — latest measurement per distinct tracked
  keyword.
- `GET /pages/{page_id}/keywords/history?keyword=...` — full history for one
  keyword, oldest first (powers the frontend's `RankHistoryChart`).
- `POST /pages/{page_id}/keywords/recheck` — rechecks every keyword already
  tracked on the page; rejects upfront with 402 if the user doesn't have
  enough credits to cover all of them (not a partial-then-fail).
- `POST /pages/{page_id}/keywords/competitors` — top organic results for a
  keyword, excluding the page's own domain. Same credit cost as a rank
  check (it's the same underlying SERP fetch).

**Why every check spends a credit even on paid plans:** REQUIREMENTS.md §3.1
only specifies *automatic* weekly/daily rank refresh for Pro/Agency as a
scheduled job. There's no "unlimited on-demand rank checks" tier the way
there is for audit rescans, so every self-serve check is metered the same
way regardless of plan. Revisit if/when automatic rank refresh gets built
alongside the scheduled-audits job below.

## AI suggestions (step 7)

- `POST /pages/{page_id}/suggestions/meta-description` and
  `POST /pages/{page_id}/suggestions/title-tag` — fetch the page's live
  HTML, send title/target keyword/a content snippet to the active AI
  provider, and return generated text matching the audit engine's own
  length thresholds for that check (120-160 chars / 30-60 chars). Spend 1
  credit on success; nothing is charged if the page fetch or the AI call
  fails. Neither is persisted to the DB — one-off suggestions for the
  frontend to show/copy, not versioned records.
- Currently `AI_PROVIDER=openai` (model: `gpt-4o-mini` - cheap/fast, plenty
  for a paragraph of copy). `anthropic` is implemented too but has no
  configured key right now.
- Content briefs (§2.7, v2) would be a new function here plus a new router
  endpoint - the provider layer doesn't change.

## Scheduled audits + alerts (§2.7, §3.1)

REQUIREMENTS.md §3.1 lists "Scheduled automated audits + alerts" as a
Pro/Agency-only perk. `run_scheduled_audits` (Celery Beat, daily at 3am UTC)
re-audits every page belonging to a Pro/Agency user and compares the new
audit to the previous one:

- **Score drop ≥10 points** → an `Alert` with `alert_type=score_drop`.
- **A check that newly started failing** (wasn't failing in the previous
  audit) → an `Alert` with `alert_type=new_fail`.

A single page's fetch failure doesn't abort the rest of the run.
`GET /alerts` lists the current user's alerts newest-first;
`POST /alerts/{id}/read` marks one read. Not credit-gated (it's an
automatic background job, not a self-serve action).

**Email delivery is not implemented** - that needs a Resend/SendGrid key we
don't have. Alerts are in-app only (`Alert` rows + the frontend's
`AlertsBell`) until one is added.

**Running this for real** needs Redis plus a Celery worker and beat process
(see "Run" above) - none of the three run automatically when you just start
`uvicorn`. Verified live in this session: started an actual worker against
a real Redis instance, seeded a Pro-plan page with a fabricated high
previous score, triggered the task, and confirmed it re-audited the page
for real (a genuine HTTP fetch), correctly computed a 30-point score drop
and a newly-failing check, and wrote both alerts to the DB.

## Default search location

`KeywordRank.location_code` defaults to **India (2356)**, not the US. Found
via a real bug: a user tracked a keyword for an India-only service and got
"not found" even though it genuinely ranked - it was checking Google.com
from a US vantage point, which is a different result set entirely. The
frontend now exposes a location/device picker on the add-keyword form
(`KeywordPanel.tsx`, `LOCATION_OPTIONS` in `lib/types.ts`) so this default
is just a starting point, not a hard limit.

## Site/page CRUD and why rank checks match against page.url, not Site.domain

Same real bug above had a second cause: rank checks used to match SERP
results against `Site.domain`, which was free text with no validation - a
typo (`"zepto"` instead of `"zepto.com"`) silently broke every check for
that site with no error, just permanent `rank_position: null`.
`check_keyword_rank` now matches against `page.url` instead, since that's
already a validated URL (the audit engine has to fetch it, so it can't be
garbage) and is more specific if a site's pages ever diverge from its
nominal domain (subdomains, redirects, etc.).

`Site.domain` now also has real format validation (`schemas.py
_clean_domain` - accepts a bare domain, a full URL, www-prefixed, etc.,
normalizes to a bare hostname, rejects anything without a valid TLD), so
the exact typo that caused this is now caught at the API boundary too, not
just worked around downstream.

## Rank provider: SerpApi vs. DataForSEO

Both are implemented; `RANK_PROVIDER=serpapi` is the current default since
DataForSEO requires a $50 minimum account top-up. SerpApi's free tier is
100 searches/month at no cost, which is what this project is currently
running on — expect rank checks to start failing with a clean 502 once
that monthly quota is used up, until either a paid SerpApi plan or
DataForSEO (`RANK_PROVIDER=dataforseo`, already verified and working) is
switched on.

## Google Search Console / Analytics integration (step 8)

Unlike the vendor keys above, this is an OAuth client, not a static API
key: Signal has to be registered as an app with Google, and then **each
user** connects their own Google account through a real consent screen -
there's no way to fully exercise this without doing the setup below.

1. Create/select a project at [console.cloud.google.com](https://console.cloud.google.com).
2. Enable **Search Console API**, **Google Analytics Data API**, and
   **Google Analytics Admin API** (APIs & Services → Library). The Admin
   API is easy to miss - it's a separate API from the Data API, needed
   only for listing which GA4 properties the connected account can see
   (`GET /integrations/google/status`); actually fetching metrics
   (`GET /pages/{id}/ga/metrics`) uses the Data API alone. Skipping it
   fails with `Google Analytics Admin API has not been used in project
   ... before or it is disabled.`
3. Configure the **OAuth consent screen** (APIs & Services → OAuth
   consent screen). While in testing mode, only Google accounts you add
   as test users can connect - fine for dev.
4. Create an **OAuth client ID** (APIs & Services → Credentials → Create
   Credentials → OAuth client ID → type "Web application"). Add
   `http://localhost:8000/integrations/google/callback` as an authorized
   redirect URI (must match `GOOGLE_REDIRECT_URI` exactly).
5. Put the resulting Client ID/Secret in `.env` as `GOOGLE_CLIENT_ID` /
   `GOOGLE_CLIENT_SECRET`.

Once configured: `POST /integrations/google/connect` (authenticated)
returns a Google consent URL; the frontend navigates the browser there;
Google redirects back to `/integrations/google/callback`, which exchanges
the code for tokens (`app/services/google_oauth.py`), stores them
encrypted (`app/services/token_crypto.py`, a Fernet key derived from
`SECRET_KEY`) in a `GoogleConnection` row, and sends the browser back to
the frontend's `/settings` page. From there the user picks which Search
Console property and GA4 property maps to each Signal site
(`Site.gsc_property` / `Site.ga_property_id`, set via the existing
`PATCH /sites/{id}`).

Data endpoints, all gated on the site having the relevant property linked:
- `GET /pages/{id}/gsc/queries` - real search queries/clicks/impressions/
  position for that exact page (`app/services/gsc.py`), a different data
  source than the SerpApi/DataForSEO rank checks: those tell you where
  *you specify* you rank, this tells you what people are *actually*
  searching that leads to clicks - including queries never manually
  tracked.
- `GET /pages/{id}/gsc/index-status` - whether Google has indexed the page
  at all, via the URL Inspection API. This is the real answer to "why does
  this page have zero rank" for a brand new page, as opposed to a ranking
  problem.
- `GET /pages/{id}/ga/metrics` - sessions/pageviews/bounce/engagement for
  that page (`app/services/ga.py`, GA4 Data API).

None of these cost Signal credits - unlike SerpApi/OpenAI, a Google API
call here doesn't cost Signal money once the OAuth grant exists, so it
isn't metered the way rank checks and AI suggestions are.

**Not yet built on top of this:** requesting indexing for an unindexed
page (a real write action via a separate Indexing API + scope, deliberately
left out of this first pass to keep the OAuth surface reviewable) and
feeding GSC query data into the Phase A opportunities list as a new
opportunity type.

## Deploying (Render)

`render.yaml` at the repo root is a Render Blueprint that deploys this
directory as a single web service (Python, `rootDir: backend`) plus a
managed Postgres database. It does **not** include Celery worker/beat or
Redis — scheduled audits (see above) are deliberately not running in
production yet; see `plan.md`'s "Not yet scheduled" for the two ways to add
them back (mirror Celery worker+beat as two more Background Workers, or
replace the daily job with a Render Cron Job) once it's worth the cost,
since Render has no free tier for either.

Steps:

1. In the Render dashboard: **New → Blueprint**, connect the
   `TeamTutx/auto-seo` GitHub repo. Render finds `render.yaml` and shows the
   `signal-api` web service + `signal-postgres` database it defines — Apply.
2. Render prompts for every env var marked `sync: false` in `render.yaml`
   during that first setup (`SERPAPI_KEY`, `OPENAI_API_KEY`,
   `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, etc. — same keys as
   `backend/.env.example`). `FRONTEND_URL`, `CORS_ORIGINS`, and
   `GOOGLE_REDIRECT_URI` depend on URLs you won't have yet at this point —
   leave them blank for now, or use placeholders, and fix them in step 4.
3. `alembic upgrade head` runs at the start of every boot, chained into
   `startCommand` (`preDeployCommand` isn't available on Render's free
   plan) — the fresh Postgres database gets its schema from the migration
   chain, not `create_all()` (see CLAUDE.md's dev-DB gotcha — that one is
   SQLite-only; Postgres here starts empty and migration-tracked from day
   one). Alembic no-ops once already at head, so this is safe to re-run on
   every cold start.
4. Once deployed, Render gives `signal-api` a URL
   (`https://signal-api-xxxx.onrender.com`). Production also has a custom
   domain, `api.signal-seo.in`: add it under Settings → Custom Domains, then at
   the DNS host add a `CNAME api → signal-api-xxxx.onrender.com` (Render shows
   the exact record; TLS is issued automatically once it resolves). Use the
   custom domain everywhere below and in the frontend's `NEXT_PUBLIC_API_URL`,
   so the API URL survives a change of Render service. Go back into the service's
   Environment settings and fill in:
   - `CORS_ORIGINS` — the real frontend origin(s), e.g.
     `https://signal-seo.in,https://www.signal-seo.in`.
   - `FRONTEND_URL` — the frontend's origin (used to build the Google OAuth
     redirect after connecting).
   - `GOOGLE_REDIRECT_URI` — `https://<this service's domain>/integrations/google/callback`
     (production: `https://api.signal-seo.in/integrations/google/callback`).
     This must **also** be added as an authorized redirect URI on the OAuth
     client in Google Cloud Console (see "Google Search Console / Analytics
     integration" above) — Google rejects the callback otherwise.
5. Render's free Postgres plan **expires 30 days after creation** (1 GB
   cap) — upgrade the database's plan before then, or the data is deleted.
   Free web services also spin down after 15 minutes idle (a real request
   wakes it back up with a several-second cold start) — fine while testing,
   worth upgrading once real users show up. `.github/workflows/keep-backend-alive.yml`
   pings `/health` every 10 minutes to prevent that spin-down for free
   (Render's own Cron Jobs need a paid plan) — GitHub Actions is free and
   unlimited for a public repo, which this one is.

## Known gaps

- Auth is homegrown JWT, not Clerk/NextAuth as REQUIREMENTS.md's stack
  table suggests — swap later if you want hosted auth.
- Stripe is deliberately not integrated yet (step 5, skipped per user
  request) — `credits_balance` is a fixed starting balance (3, from
  registration) with no way to top up or renew monthly. The credit-gating
  logic itself (check balance → decrement → 402 when empty) is already
  built the same way it'll work once Stripe adds a way to refill it.
- AI suggestions cover meta descriptions and title tags only - no content
  briefs yet (§2.7, v2).
- GSC/GA integration (step 8) is built but unverified against real Google
  data - see "Google Search Console / Analytics integration" above for the
  setup that's still needed before it can be tested live.
- No keyword-suggestion features (search volume/difficulty, §2.4) - needs a
  funded keyword-data API; DataForSEO is set up but blocked on that $50
  top-up, and SerpApi doesn't offer this data in a compatible way.
- Email alerts not implemented - needs a Resend/SendGrid key. In-app alerts
  work today; see "Scheduled audits + alerts" above.
- Redis/Celery worker/beat aren't run automatically - they're separate
  processes you start manually (or via `brew services`/a process manager)
  alongside `uvicorn`. Nothing breaks if they're not running; scheduled
  audits and alerts simply won't happen.
- Not provisioned on the Render deployment at all (see "Deploying (Render)"
  below) - deliberately deferred since Render has no free tier for
  Background Workers/Cron Jobs and nothing else uses Celery yet.
