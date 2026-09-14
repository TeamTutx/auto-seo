# Signal — Self-Serve SEO Platform

A website that lets users run SEO audits, track rankings, and get
AI-assisted fixes for their own web pages.

- Full requirements: [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md)
- UI mockup: [`frontend/seo-dashboard-mockup.html`](frontend/seo-dashboard-mockup.html)
- Backend: [`backend/`](backend/README.md)
- Frontend: [`frontend/`](frontend/README.md)

## Status
Steps 1-4, 6, and most of 7 of the [suggested build order](docs/REQUIREMENTS.md#8-suggested-build-order)
are done, fully wired frontend-to-backend, plus two pieces pulled forward
from later sections: site domain verification (§2.1) and competitor
comparison (§2.4). Concretely: DB schema, FastAPI scaffold + auth, the
on-page audit engine, a Next.js dashboard (add/edit/delete sites and pages,
run an audit, see the score and checklist), keyword rank tracking with a
location/device picker (add/list/recheck a keyword, see its live rank,
rank-history chart, competitor list), AI-generated meta description and
title suggestions, domain verification (DNS TXT/meta tag/file upload), and
scheduled Pro/Agency audits that raise in-app alerts on a regression
(needs Redis + a Celery worker + beat process running - see
`backend/README.md`).

Rank tracking and AI suggestions both sit behind swappable vendor
interfaces (rank: SerpApi/DataForSEO; AI: OpenAI/Anthropic) picked by one
env var each. Step 5 (Stripe) is deliberately skipped for now, to be added
before going live.

**Not started:** content briefs (§2.7 v2), keyword search-volume/difficulty
suggestions (§2.4 - blocked on a funded keyword-data API), GSC/GA
integrations (step 8 - blocked on Google OAuth credentials), email alert
delivery (blocked on a Resend/SendGrid key - alerts are in-app only for
now), team/agency multi-user seats.

## Stack
- Backend: Python (FastAPI, SQLModel, Celery + Redis for scheduled audits —
  see [`backend/README.md`](backend/README.md))
- Frontend: Next.js (App Router)
- DB: SQLite for local dev, PostgreSQL via `DATABASE_URL` for anything real
- Billing: Stripe (not yet integrated)
