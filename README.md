# Signal — Self-Serve SEO Platform

A website that lets users run SEO audits, track rankings, and get
AI-assisted fixes for their own web pages.

- Full requirements: [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md)
- UI mockup: [`frontend/seo-dashboard-mockup.html`](frontend/seo-dashboard-mockup.html)
- Backend: [`backend/`](backend/README.md)
- Frontend: [`frontend/`](frontend/README.md)

## Status
Steps 1-4, 6, and part of 7 of the [suggested build order](docs/REQUIREMENTS.md#8-suggested-build-order)
are done: DB schema, FastAPI scaffold + auth, the on-page audit engine, a
Next.js dashboard wired to real data (add a site, add a page, run an audit,
see the score and checklist), keyword rank tracking, and AI-generated meta
description suggestions — the last two both backend-only so far (no
frontend UI yet) and both behind swappable vendor interfaces (rank:
SerpApi/DataForSEO; AI: OpenAI/Anthropic) picked by one env var each. Step 5
(Stripe) is deliberately skipped for now, to be added before going live.
Not started: title rewrites/content briefs, GSC/GA integrations.

## Stack
- Backend: Python (FastAPI, SQLModel, Celery scaffolded but not wired in —
  see [`backend/README.md`](backend/README.md))
- Frontend: Next.js (App Router)
- DB: SQLite for local dev, PostgreSQL via `DATABASE_URL` for anything real
- Billing: Stripe (not yet integrated)
