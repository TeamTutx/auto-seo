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
- `app/login/` — "Continue with Google" (a whole-tab navigation to the API's
  `/auth/google/start`), which comes back here with the token in the URL fragment.
  The email/password form is the fallback, at `/login?password=1`.
- `app/(dashboard)/layout.tsx` + `components/Sidebar.tsx` — auth-gated shell:
  sites list, credits widget, add-site form.
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
  `/keywords/competitors` endpoint). Surfaces the backend's account-limit and
  credit-exhaustion errors inline the same way the rest of the dashboard
  does.
- `components/AlertsBell.tsx` — in the sidebar's credits widget: a badge with
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
navigates to the right page. Also hit the site-limit (402) and fetch-failure
(502) errors and confirmed they render as inline messages. ("Run full scan"
now lists the page and the reason for each failure rather than a count.)

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

## Deploying (Render static site)

The app is a **static export** (`next.config.mjs` sets `output: "export"`),
published to Render's CDN. What that buys: it's free on Render's Hobby plan,
it never spins down (unlike a free *web service*, which sleeps after 15
minutes and takes ~a minute to wake — fatal for pages you want crawled), and
the public pages are served as files.

What it costs, and what you must not break:

- **No server at request time.** No route handlers (`app/api/*`), no ISR/
  `revalidate`, no `next/headers`, no server-side dynamic rendering.
- **No dynamic route segments** unless they can be enumerated at build time.
  Per-user ids can't be, which is why the dashboard passes them in the query
  string — see `lib/routes.ts`, and add new id-carrying routes there.
- **Prices are baked in at build time.** The landing page fetches
  `GET /pricing` during the build, so the API must be reachable when Render
  builds. An edit in `/admin/pricing` triggers a rebuild through a deploy hook
  (`backend/app/services/site_rebuild.py`); without the hook configured,
  prices refresh on the next deploy.

**Why not Vercel:** its free Hobby plan forbids commercial use, and Signal
sells credits. Its free plan also refuses to connect a project to a repo owned
by a GitHub *Organization* (`TeamTutx/auto-seo` is one) without Pro.

**Why not Netlify any more:** the free plan is 300 credits/month and a
production deploy costs 15 of them (~20 deploys), with bandwidth at 20
credits/GB. Exceeding it **pauses the site** until the next billing cycle —
and pauses every other project on the account with it.

### First deploy

1. `render.yaml` already defines the `signal-site` service. In the Render
   dashboard, **Blueprints → the blueprint for this repo → Apply** picks it up
   alongside `signal-api`. Or create it by hand: **New → Static Site**, root
   directory `frontend`, build command `npm ci && npm run build`, publish
   directory `out`.
2. Set the build-time env vars (the blueprint sets the first two):
   - `NEXT_PUBLIC_API_URL` = `https://api.signal-seo.in`, no trailing slash.
   - `NEXT_PUBLIC_SITE_URL` = `https://signal-seo.in` — the origin used for
     canonical URLs, `/sitemap.xml` and `/robots.txt`.
   - Optional `NEXT_PUBLIC_GA_ID` = the GA4 measurement ID (`G-XXXXXXXXXX`,
     public by design). Unset means no tracking tag; malformed values are
     ignored rather than injected.
   All three are inlined into the bundle, so changing one needs a rebuild.
3. Render gives you an `onrender.com` URL. **Check it before moving DNS** —
   in particular `/auto-seo-tools` and `/terms` (extensionless paths resolving
   to the exported `.html` files) and one dashboard URL with a query string.
4. Backend (`signal-api` → Environment), once the URL exists:
   - `CORS_ORIGINS` — comma-separated, e.g.
     `https://signal-seo.in,https://signal-site.onrender.com`.
   - `FRONTEND_URL` — same origin, used to build the Google OAuth redirect.
   Skip these and every API call fails from the browser even though both
   services are healthy.
   - Optional `RENDER_DEPLOY_HOOK_URL` — the static site's deploy hook
     (**Settings → Deploy Hook**). With it set, a pricing change rebuilds the
     landing page automatically. It's a credential: anyone holding it can
     spend your build minutes, which is why it lives on the API and never in
     the frontend bundle.
5. Custom domain (`signal-seo.in`, bought via GoDaddy): add it under the
   static site's **Settings → Custom Domains**; Render prints the exact DNS
   records to add at GoDaddy. Do this last, and only once step 3 passed.

### Old dashboard URLs

`/dashboard/sites/:id/...` and `/admin/users/:id` are *rewritten* (not
redirected) to `/legacy-link`, which reads the original path — still in the
address bar, because it's a rewrite — and forwards to the query-string URL.
The rules live in `render.yaml`; the mapping lives in `legacyPathToRoute`
(`lib/routes.ts`).

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

## Admin, billing and legal pages

- `app/admin/*` — owner-only panel: **Overview** (users, revenue, paying users, estimated
  MRR, credits outstanding/spent), **Users** (search, plan/paid filters, sortable, paginated)
  and **user detail** (add/remove credits with a required reason, record a manual payment,
  change plan, payments / credit history / audit trail), and **Pricing & plans** (edit
  prices, names, credit-pack sizes, link Dodo product ids, "Check against Dodo"). The layout
  bounces non-admins, but the API is the real gate (`ADMIN_EMAILS`). Saving pricing calls
  `app/api/revalidate-pricing` so the public page updates immediately.
- `app/dashboard/billing` — a customer's plan, credits, upgrade/buy buttons (hosted Dodo
  checkout), "Manage billing" (Dodo customer portal) and payment history. After checkout it
  polls briefly, because the webhook that grants the plan can land a few seconds after the
  redirect.
- `app/page.tsx` fetches `GET /pricing` on the server (5-minute cache + on-demand
  revalidation) and hands it to `app/landing-page.tsx`; `lib/default-pricing.ts` is the
  fallback if the API is down.
- `app/(legal)/` — `/terms`, `/privacy`, `/refunds`. Required by Dodo before it approves an
  account; they're drafts written to match what the product does, so have them reviewed.
- Optional env: `NEXT_PUBLIC_SUPPORT_EMAIL` (defaults to the owner's address; shown on the
  legal pages and footer).
