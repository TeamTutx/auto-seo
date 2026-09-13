# Signal backend

FastAPI service covering steps 1-4 and 6 of the build order in
[`../docs/REQUIREMENTS.md`](../docs/REQUIREMENTS.md#8-suggested-build-order):
DB schema, API scaffold + auth, the on-page audit engine, and keyword rank
tracking via DataForSEO. Step 5 (Stripe) is deliberately skipped for now —
see "Known gaps" below.

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

`app/services/audit_engine.py` and `app/services/rank_provider.py` have
pure unit tests (no DB/network - HTML or a fixture JSON response in,
findings out). `tests/test_keywords_api.py` exercises the full keywords API
through FastAPI's `TestClient` against an in-memory SQLite DB, with
`rank_provider.fetch_rank` monkeypatched so it never calls DataForSEO for
real. Everything else (auth, sites, pages, audits routers) is still only
exercised manually — no fixtures/test DB wired up for those yet.

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
- `app/services/rank_provider.py` — DataForSEO SERP client (§2.4, §7). Split
  into `extract_rank` (pure response parsing, unit tested) and `fetch_rank`
  (the actual HTTP call, needs `DATAFORSEO_LOGIN`/`DATAFORSEO_PASSWORD` in
  `.env` — untested here since it costs real money per request).
- `app/services/keyword_rank_runner.py` — persists one rank check
  (`KeywordRank` row) for a page; called from the keywords router.
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
