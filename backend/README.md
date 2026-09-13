# Signal backend

FastAPI service covering steps 1-3 of the build order in
[`../docs/REQUIREMENTS.md`](../docs/REQUIREMENTS.md#8-suggested-build-order):
DB schema, API scaffold + auth, and the on-page audit engine.

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

Only `app/services/audit_engine.py` has unit tests so far — it's pure
(HTML in, findings out) so it doesn't need a DB or network to test. The
rest of the API is exercised manually for now; no fixtures/test DB wired up
yet.

## What's here

- `app/models.py` — SQLModel schema: `User`, `Site`, `Page`, `Audit`,
  `Check`, `KeywordRank`, plus `PLAN_LIMITS` for free/pro/agency gating.
- `app/routers/` — `auth` (register/login/me, JWT), `sites`, `pages`,
  `audits`. Plan limits (§3.1) and the free-tier 1x/day rescan throttle are
  enforced in the routers.
- `app/services/audit_engine.py` — the on-page audit checks from §2.2
  (title, meta description, headings, alt text, links, content length,
  keyword density, readability, canonical, robots meta, structured data).
- `app/services/audit_runner.py` — fetches a page's HTML and persists an
  `Audit` + its `Check` rows; called directly from the audits router today.
- `app/workers/` — Celery app + a `run_page_audit` task wrapping the same
  runner, not wired into the API yet (see comment in `tasks.py`).
- `alembic/` — hand-written initial migration (no live Postgres to
  autogenerate against yet); regenerate if it drifts from `models.py`.

## Known gaps (not part of steps 1-3)

- Auth is homegrown JWT, not Clerk/NextAuth as REQUIREMENTS.md's stack
  table suggests — swap later if you want hosted auth.
- Site domain verification (DNS TXT / meta tag / file upload, §2.1) isn't
  implemented — `Site.verified` stays `false`.
- No Stripe, rank-tracking provider, or Claude integration yet (steps 5-7).
