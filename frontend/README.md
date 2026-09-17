# Signal frontend

Next.js (App Router) dashboard wired to the [backend](../backend) API —
steps 4, 6, and most of 7 of the build order in
[`../docs/REQUIREMENTS.md`](../docs/REQUIREMENTS.md#8-suggested-build-order),
plus site verification (§2.1) and competitor comparison (§2.4).
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
  pieces shared between the two dashboard views. `CheckList` drives the
  "Generate a [meta description/title] suggestion →" action on the
  `meta_description` and `title_tag` checks: calls the matching AI-suggestion
  endpoint, shows the result inline with a copy button. Not persisted
  anywhere — re-navigating away loses it, matching the backend (nothing is
  stored server-side either).
- `components/SiteVerification.tsx` — domain ownership verification (§2.1)
  on the site overview page: pick a method (DNS TXT / meta tag / file
  upload), see the exact instructions for that method using the site's real
  token, "Check now" to verify. Shows a "Verified" badge once it succeeds.
- `components/KeywordPanel.tsx` — keyword rank tracking (step 6), shown on
  the page detail view regardless of whether an audit has run yet: add a
  keyword (with a location/device picker - defaults to India, see
  `backend/README.md`), see the latest rank per tracked keyword, "Recheck
  rankings now" to refresh all of them. Each tracked keyword expands into
  two tabs: **History** (`components/RankHistoryChart.tsx`, a small inline
  SVG line chart from the `/keywords/history` endpoint) and **Competitors**
  (top organic results excluding your own domain, from the new
  `/keywords/competitors` endpoint). Surfaces the backend's plan-limit and
  credit-exhaustion errors inline the same way the rest of the dashboard
  does.
- `components/AlertsBell.tsx` — in the sidebar's plan widget: a badge with
  the unread count from `GET /alerts`, polled every 60s so a scheduled-audit
  alert (see `backend/README.md`) shows up without a manual refresh.
  Clicking an alert marks it read and navigates straight to the page it's
  about. Closes on an outside click.

Verified manually end-to-end in a real browser: register → add site (with
domain validation/normalization) → verify it via a real DNS TXT lookup
(correctly reports "not verified" against a real domain with no matching
record) → add a page → run a real audit → generate real AI meta
description and title suggestions → track a keyword with India as the
location → see its live rank → expand it to see history and a real
competitor list (own domain correctly excluded) → edit a site's domain and
a page's url/keyword → delete a page → delete a site and confirm the
sidebar updates without a reload → open a real alert (seeded by an actual
Celery worker run against real Redis) and confirm it marks read and
navigates to the right page. Also hit the free-tier site-limit (402) and
rescan-throttle (429) errors and confirmed they render as inline messages.

Two things worth knowing if you're driving this with browser automation
rather than a human:
- `window.confirm()` (used for both delete confirmations) doesn't surface
  in automated/headless testing - override it via injected JS
  (`window.confirm = () => true`) to verify the delete flows. Works
  normally for a real user in a real browser.
- A long-lived tab in this session started producing bizarre, incorrect
  screenshots (page content shrunk into a corner) despite the DOM/viewport
  reporting completely normal values via `read_page`/`window.innerWidth` -
  purely a rendering artifact of that specific tab after a lot of
  navigation, not a real bug. A fresh tab rendered correctly every time.
  Worth knowing so you don't chase a phantom bug: if a screenshot looks
  wrong but `read_page` and DOM introspection say the state is correct,
  open a new tab before concluding there's an actual problem.

## Deploying (Vercel)

No code changes needed — the app already reads its API base URL from
`NEXT_PUBLIC_API_URL` (`lib/api.ts`, defaults to `http://localhost:8000` for
local dev) and `next.config.js` has no custom build behavior, so it's a
standard Vercel import.

1. In the Vercel dashboard: **Add New → Project**, import the
   `TeamTutx/auto-seo` GitHub repo.
2. This is a monorepo (frontend + backend in one repo) — set **Root
   Directory** to `frontend` in the import screen (or Project Settings →
   General → Root Directory afterwards). Framework preset should
   auto-detect as Next.js; build/output/install commands can stay default.
3. Add one environment variable before deploying:
   - `NEXT_PUBLIC_API_URL` — the Render backend's URL (e.g.
     `https://signal-api-xxxx.onrender.com`, or `https://api.signal-seo.in`
     once that custom domain is attached — see backend/README.md
     "Deploying (Render)"). No trailing slash.
4. Deploy. Vercel gives you a `*.vercel.app` URL immediately.
5. Go back to the **backend** (Render dashboard → `signal-api` →
   Environment) and fill in, now that this URL exists:
   - `CORS_ORIGINS` — this Vercel URL (and your custom domain once attached,
     comma-separated: `https://signal-seo.in,https://<project>.vercel.app`).
   - `FRONTEND_URL` — same origin, used to build the Google OAuth redirect.
   Without this the browser console will show CORS errors on every API call
   and the app will look broken even though both services are up.
6. Custom domain (`signal-seo.in`, bought via GoDaddy): add it under Vercel
   Project Settings → Domains — Vercel gives you the exact DNS records to
   add. Change `signal-seo.in`'s DNS at GoDaddy (either add those records
   directly there, or move the domain's nameservers to Vercel/Cloudflare
   first if you want to manage DNS elsewhere) rather than at the registrar's
   own DNS panel if you've moved nameservers away from GoDaddy.

## Known gaps

- No credit-pack / upgrade modal — billing is step 5, intentionally
  skipped for now.
- Data fetching is plain client-side `useEffect` + `fetch`, not
  SSR/React Query — fine at this scale, worth revisiting if pages get slow.
- "Run full scan" re-audits pages sequentially (not parallel, not queued
  through Celery) — fine for a handful of pages, not for hundreds.
- No GSC/GA connection UI (step 8) — blocked on Google OAuth credentials,
  see `backend/README.md`.
- No dedicated alerts page - `AlertsBell` is a quick list, not a full
  history/filter view.
