# Signal frontend

Next.js (App Router) dashboard wired to the [backend](../backend) API — step 4
of the build order in [`../docs/REQUIREMENTS.md`](../docs/REQUIREMENTS.md#8-suggested-build-order).
The static design reference is still at
[`seo-dashboard-mockup.html`](seo-dashboard-mockup.html); this app implements
that design against real data instead of hardcoded fixtures.

## Requirements

Node **>= 18.17** (the repo's default system Node may be older — check with
`node --version` before running `npm install`).

## Setup

```bash
npm install
cp .env.local.example .env.local
```

`NEXT_PUBLIC_API_URL` in `.env.local` should point at the running backend
(defaults to `http://localhost:8000`).

## Run

```bash
npm run dev
```

Requires the [backend](../backend) running separately (`uvicorn app.main:app`)
with CORS already configured for `http://localhost:3000` in
`backend/app/main.py`.

## What's here

- `lib/api.ts` — typed fetch wrapper for every backend endpoint used so far
  (auth, sites, pages, audits). Stores the JWT in `localStorage`.
- `lib/auth-context.tsx` — React context exposing `user`/`login`/`register`/`logout`.
- `app/login/` — combined login/register form.
- `app/(dashboard)/layout.tsx` + `components/Sidebar.tsx` — auth-gated shell:
  sites list, plan/credits widget, add-site form.
- `app/(dashboard)/sites/[siteId]/page.tsx` — site overview: score gauge
  (average of pages' latest audit scores), stat row, pages table, add-page
  form, "Run full scan" (re-audits every page on the site).
- `app/(dashboard)/sites/[siteId]/pages/[pageId]/page.tsx` — page detail:
  full checklist from the on-page audit engine, rescan button.
- `components/ScoreGauge.tsx`, `components/CheckList.tsx` — presentational
  pieces shared between the two dashboard views.

Verified manually end-to-end in a real browser: register → add site → add
page → run a real audit against a live URL → see the checklist and score →
hit both the free-tier site-limit (402) and rescan-throttle (429) errors and
confirmed they render as inline messages.

## Known gaps (not part of step 4)

- No rank-tracking UI yet (keyword panel from the mockup) — that's step 6.
- No credit-pack / upgrade modal — billing is step 5.
- Data fetching is plain client-side `useEffect` + `fetch`, not
  SSR/React Query — fine at this scale, worth revisiting if pages get slow.
- "Run full scan" re-audits pages sequentially (not parallel, not queued
  through Celery) — fine for a handful of pages, not for hundreds.
