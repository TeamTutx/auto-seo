# Signal frontend

Next.js (App Router) dashboard wired to the [backend](../backend) API —
steps 4, 6, and part of 7 of the build order in
[`../docs/REQUIREMENTS.md`](../docs/REQUIREMENTS.md#8-suggested-build-order).
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
  (auth, sites, pages, audits, keywords, AI suggestions), including
  `update`/`delete` for sites and pages. Stores the JWT in `localStorage`.
- `lib/auth-context.tsx` — React context exposing `user`/`login`/`register`/`logout`.
- `lib/sites-context.tsx` — React context holding the sites list, shared by
  the sidebar and every page that lists/mutates sites. Without this, editing
  or deleting a site on the overview page left the sidebar showing stale
  data until a full reload — any component that mutates a site must call
  `refreshSites()` afterward.
- `app/login/` — combined login/register form.
- `app/(dashboard)/layout.tsx` + `components/Sidebar.tsx` — auth-gated shell:
  sites list, plan/credits widget, add-site form.
- `app/(dashboard)/sites/[siteId]/page.tsx` — site overview: score gauge
  (average of pages' latest audit scores), stat row, pages table, add-page
  form, "Run full scan" (re-audits every page on the site), inline domain
  edit, delete-site (confirm dialog, cascades on the backend), per-row
  delete-page.
- `app/(dashboard)/sites/[siteId]/pages/[pageId]/page.tsx` — page detail:
  full checklist from the on-page audit engine, rescan button, inline
  url/target-keyword edit, delete-page (confirm dialog, redirects to the
  site overview).
- `components/ScoreGauge.tsx`, `components/CheckList.tsx` — presentational
  pieces shared between the two dashboard views. `CheckList` also drives the
  "Generate a suggestion →" action on the `meta_description` check (step 7):
  calls the AI-suggestion endpoint, shows the result inline with a copy
  button. Not persisted anywhere — re-navigating away loses it, matching the
  backend (nothing is stored server-side either).
- `components/KeywordPanel.tsx` — keyword rank tracking (step 6), shown on
  the page detail view regardless of whether an audit has run yet: add a
  keyword (runs its first check), see the latest rank per tracked keyword,
  "Recheck rankings now" to refresh all of them. Surfaces the backend's
  plan-limit and credit-exhaustion errors inline the same way the rest of
  the dashboard does.

Verified manually end-to-end in a real browser: register → add site → add
page → run a real audit against a live URL → see the checklist and score →
generate a real AI meta-description suggestion → track a keyword and see
its live rank → recheck it → edit a site's domain and a page's url/keyword
→ delete a page → delete a site and confirm the sidebar updates without a
reload. Also hit the free-tier site-limit (402) and rescan-throttle (429)
errors and confirmed they render as inline messages.

Note: `window.confirm()` (used for both delete confirmations) doesn't
surface in automated/headless browser testing - had to override it via
injected JS (`window.confirm = () => true`) to verify the delete flows.
Works normally for a real user in a real browser.

## Known gaps

- No credit-pack / upgrade modal — billing is step 5, intentionally
  skipped for now.
- Data fetching is plain client-side `useEffect` + `fetch`, not
  SSR/React Query — fine at this scale, worth revisiting if pages get slow.
- "Run full scan" re-audits pages sequentially (not parallel, not queued
  through Celery) — fine for a handful of pages, not for hundreds.
- No rank-history chart (§2.5) yet, even though the backend already has a
  `history` endpoint for it — only the latest rank per keyword is shown.
