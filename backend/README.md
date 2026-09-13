# Signal backend

FastAPI service covering steps 1-4 and 6 of the build order in
[`../docs/REQUIREMENTS.md`](../docs/REQUIREMENTS.md#8-suggested-build-order):
DB schema, API scaffold + auth, the on-page audit engine, and keyword rank
tracking (currently via SerpApi, swappable - see below). Step 5 (Stripe) is
deliberately skipped for now — see "Known gaps" below.

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

## Test

```bash
pytest
```

`app/services/audit_engine.py` and both `app/services/rank_providers/*`
implementations have pure unit tests (no DB/network - HTML or a fixture
JSON response in, findings out). `tests/test_keywords_api.py` exercises the
full keywords API through FastAPI's `TestClient` against an in-memory
SQLite DB, with `get_rank_provider()` monkeypatched to a fake provider so
it never calls a real rank-data vendor. Everything else (auth, sites,
pages, audits routers) is still only exercised manually — no fixtures/test
DB wired up for those yet.

## What's here

- `app/models.py` — SQLModel schema: `User`, `Site`, `Page`, `Audit`,
  `Check`, `KeywordRank`, plus `PLAN_LIMITS` for free/pro/agency gating.
- `app/routers/` — `auth` (register/login/me, JWT), `sites`, `pages`,
  `audits`, `keywords`. Plan limits (§3.1), the free-tier 1x/day rescan
  throttle, and per-check credit spend are enforced in the routers.
- `app/services/audit_engine.py` — the on-page audit checks from §2.2
  (title, meta description, headings, alt text, links, content length,
  keyword density, readability, canonical, robots meta, structured data).
- `app/services/audit_runner.py` — fetches a page's HTML and persists an
  `Audit` + its `Check` rows; called directly from the audits router today.
- `app/services/rank_providers/` — rank-data vendor integrations (§2.4, §7),
  behind one interface so swapping vendors doesn't touch calling code:
  - `base.py` — the `RankProvider` ABC (one method: `fetch_rank`) plus the
    shared `normalize_domain` helper used to match a SERP result to a site.
  - `dataforseo.py`, `serpapi.py` — one class per vendor. Each is split into
    the actual HTTP call (needs real credentials, untested here since it
    costs real money per request) and a `extract_rank` static method (pure
    response parsing, unit tested against fixture JSON).
  - `__init__.py` — `get_rank_provider()` reads `RANK_PROVIDER` from config
    and returns the matching instance; this is the only thing the rest of
    the app calls. **To add a vendor**: subclass `RankProvider`, register it
    in `_PROVIDERS`, add its credentials to `config.py`/`.env`. **To switch
    the active one**: change `RANK_PROVIDER` in `.env` — nothing else.
- `app/services/keyword_rank_runner.py` — persists one rank check
  (`KeywordRank` row) for a page, tagged with whichever provider ran it, so
  historical rows stay accurate even after switching vendors later.
- `app/workers/` — Celery app + a `run_page_audit` task wrapping the audit
  runner, not wired into the API yet (see comment in `tasks.py`).
- `alembic/` — hand-written migrations (no live Postgres to autogenerate
  against yet); regenerate if they drift from `models.py`.

## Keyword rank tracking (step 6)

- `POST /pages/{page_id}/keywords` — track a keyword and run its first
  check. New keyword strings count against the plan's
  `max_keywords_per_page` (free: 3); rechecking an already-tracked keyword
  doesn't. Every check (new or recheck) spends 1 credit from
  `User.credits_balance` regardless of plan — see the note below.
- `GET /pages/{page_id}/keywords` — latest measurement per distinct tracked
  keyword.
- `GET /pages/{page_id}/keywords/history?keyword=...` — full history for one
  keyword, oldest first (for the rank-over-time chart in §2.5, not built yet).
- `POST /pages/{page_id}/keywords/recheck` — rechecks every keyword already
  tracked on the page; rejects upfront with 402 if the user doesn't have
  enough credits to cover all of them (not a partial-then-fail).

**Why every check spends a credit even on paid plans:** REQUIREMENTS.md §3.1
only specifies *automatic* weekly/daily rank refresh for Pro/Agency (a
scheduled job, not built yet — see `app/workers/tasks.py`). There's no
"unlimited on-demand rank checks" tier the way there is for audit rescans,
so for now every check (self-serve or automatic, once that exists) is
metered the same way. Revisit this once the scheduled-refresh job exists.

## Rank provider: SerpApi vs. DataForSEO

Both are implemented; `RANK_PROVIDER=serpapi` is the current default since
DataForSEO requires a $50 minimum account top-up. SerpApi's free tier is
100 searches/month at no cost, which is what this project is currently
running on — expect rank checks to start failing with a clean 502 once
that monthly quota is used up, until either a paid SerpApi plan or
DataForSEO (`RANK_PROVIDER=dataforseo`, already verified and working) is
switched on.

## Known gaps (not part of steps 1-4, 6)

- Auth is homegrown JWT, not Clerk/NextAuth as REQUIREMENTS.md's stack
  table suggests — swap later if you want hosted auth.
- Site domain verification (DNS TXT / meta tag / file upload, §2.1) isn't
  implemented — `Site.verified` stays `false`.
- Stripe is deliberately not integrated yet (step 5, skipped per user
  request) — `credits_balance` is a fixed starting balance (3, from
  registration) with no way to top up or renew monthly. The credit-gating
  logic itself (check balance → decrement → 402 when empty) is already
  built the same way it'll work once Stripe adds a way to refill it.
- No Claude API integration (AI suggestions, step 7) or GSC/GA
  integrations (step 8) yet.
- No keyword-suggestion or competitor-comparison features (§2.4) — only
  rank checks for keywords the user explicitly adds.
