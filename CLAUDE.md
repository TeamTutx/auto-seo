# Signal — working notes for Claude Code

Self-serve SEO platform. FastAPI backend (`backend/`) + Next.js App Router
frontend (`frontend/`). Full feature/roadmap history lives in `plan.md` —
read that for what's built, what's deliberately deferred, and why.

## Landing page parity

`frontend/app/landing-page.tsx` (rendered by the public `/` route in `app/page.tsx`,
which is a thin server wrapper owning the page's canonical URL and JSON-LD) is a marketing page that
visually explains the product using stylized recreations of the real
dashboard UI — score gauges, check cards, rank charts, opportunity lists,
GSC/GA panels, etc. Its styles live in `frontend/app/globals.css` under the
`.lp-*` prefixed rules (namespaced so they can't leak into the dashboard).

**Whenever a UI or feature change touches something the landing page depicts
or claims, update the landing page to match, as part of that same change —
don't leave it stale.** Concretely:

- New feature shipped in the dashboard → decide whether it earns its own
  `lp-feature-row` (or a full-width "deep dive" `lp-feature-row full`) or
  just a line in the `lp-strip` "also included" row, and add it.
- The site page leads with `SearchPresencePanel` (Google + AI gauges and the home page's
  Search Console trend, from `GET /sites/{id}/presence`) where the opportunities list used
  to be; `OpportunitiesPanel` now sits below the pages it refers to. The presence endpoint
  never spends a credit, so the page stays free to open.
- Anything the site page shows about crawling, index status, keyword ideas or visibility
  is fed by `app/routers/discovery.py`. What each action costs is listed in two places
  the user reads — `CREDIT_COSTS` on the landing page and the "What a credit buys" panel
  on `/dashboard/billing` — so a new metered action means editing both.
- Pricing: **Signal sells credits and nothing else** — there are no tiers and nothing
  recurring. The pricing section renders `GET /pricing`, which returns the active rows of
  the `Product` table (credit packs the owner creates, prices, reorders and retires in
  `/admin/pricing`) plus `ACCOUNT_LIMITS` in `backend/app/models.py`, which apply to every
  account equally. So a price, limit or *new pack* needs no landing edit — the grid sizes
  itself to however many packs exist. `lib/default-pricing.ts` is the fallback shown when
  the API is unreachable; keep it in step with the migration's seeded ladder.
- `CREDIT_COSTS` in `landing-page.tsx` is the public list of what each action costs. It
  mirrors the real `deduct_credit()` calls in `backend/app/routers/{keywords,suggestions}.py`
  — change one and change the other, or the pricing page is lying about prices. The same
  list appears on `/dashboard/billing`.
- Never list a benefit that isn't running in production. Scheduled audits + alerts are
  built but not deployed (see plan.md "Not yet scheduled"), so they are deliberately *not*
  in the "also included" strip — re-add them only once the cron job is actually
  provisioned.
- A concept gets renamed or removed (e.g. "Opportunities" becomes something
  else) → update the matching `lp-feature-tag` and copy.
- Auth/routing changes → the landing page's CTAs branch on `useAuth()`'s
  `user` (logged in → "Go to dashboard" / `/dashboard`; logged out →
  `/login` and `/login?mode=register`). Keep that logic in sync with
  `lib/auth-context.tsx` and the `/dashboard` route group.

Don't invent claims the product doesn't back — every visual on the landing
page today is a stylized recreation of a real, shipped feature (see
`plan.md`'s phase notes), not aspirational copy. If a landing-page update
would require inventing a feature, build the feature (or note it as
explicitly not-yet-built, matching `plan.md`'s convention) rather than just
writing copy for it.

## Routing

- `/` — public landing page (`app/landing-page.tsx` via `app/page.tsx`), not auth-gated.
  `app/robots.ts` / `app/sitemap.ts` serve `/robots.txt` and `/sitemap.xml`
  (public origin from `lib/site.ts`; `/dashboard` is disallowed).
  Also public: `/terms`, `/privacy`, `/refunds` (route group `app/(legal)/`, required by
  the payment provider — Dodo won't approve an account without them, pricing and a
  contact address; the contact is `SUPPORT_EMAIL` in `lib/site.ts`).
- `/login` — **"Continue with Google" is the only advertised way in**
  (`GET /auth/google/start` → Google → `/auth/google/callback`, which redirects back
  here with the token in the URL *fragment*; the page reads it, stores it and scrubs the
  address bar). Email + password still works at `/login?password=1` and the
  `/auth/register` + `/auth/login` endpoints are untouched — that's the deliberate way
  back in if the OAuth client is ever misconfigured, so don't delete it. Redirects to
  `/dashboard` if already authenticated.
  Signing in asks Google for `openid email profile` only; Search Console/Analytics
  access is a **separate** consent from Settings, with its own redirect URI
  (`GOOGLE_LOGIN_REDIRECT_URI` vs `GOOGLE_REDIRECT_URI`). Accounts are matched by
  verified email, so Google sign-in lands in an existing password account rather than
  making a second one.
- `/dashboard/*` — the actual product (sites, pages, settings), gated by
  `app/dashboard/layout.tsx` (redirects to `/login` if unauthenticated).
  `/dashboard/sites/[siteId]/keywords` (keyword ideas + which ones to target) and
  `/dashboard/sites/[siteId]/visibility` (Google / AI Overview / ChatGPT) are the two
  pages driven by background jobs — see the gotcha below.
  This used to be a route group living at `/` before the landing page
  existed — if you ever run across old links to `/sites/...` or `/settings`
  (missing the `/dashboard` prefix), they're stale and need fixing.
  `/dashboard/billing` is the customer's credits/payment page (buy a pack, history).
- `/admin/*` — the owner-only panel (users, payments, credits, credit packs), client-gated by
  `app/admin/layout.tsx` and **really** gated by the API: every `/admin/*` route needs the
  caller's email in `ADMIN_EMAILS`. `/admin` is disallowed in `robots.ts`.
- `app/api/revalidate-pricing` — admin-only Next route that refreshes the landing page's
  cached pricing right after an edit in `/admin/pricing`.

## Dev gotchas

- **Never run `npm run build` while `npm run dev` is also running against
  the same `.next` directory** — it corrupts webpack chunk references
  (`Cannot find module './NNN.js'`, pages failing to render). Fix: kill both
  (`pkill -f "next-server"; pkill -f "next dev"`), `rm -rf frontend/.next`,
  restart `npm run dev`.
- The dev SQLite DB (`backend/signal.db`) was created via
  `SQLModel.metadata.create_all()`, not via Alembic — it has no migration
  history (`alembic current` shows nothing there). `create_all()` only adds
  *missing tables*, it does not add new columns to existing ones. After
  adding a column to an existing model, either apply it manually
  (`ALTER TABLE ... ADD COLUMN ...`) against the dev DB or rebuild it — don't
  assume writing the Alembic migration alone fixes the running dev DB.
- **Background jobs run in the API process**, not a worker: crawling, keyword discovery
  and visibility checks all go through `app/services/site_jobs.py` via FastAPI's
  `BackgroundTasks` (Render's free tier has no worker). Consequences that bite:
  a job needs its *own* session — `site_jobs.session_factory()`, because the request's
  session is closed by the time it runs, and `tests/conftest.py` repoints that factory
  at the test engine or jobs would write to the real database. Progress must be
  committed as it happens or the polling UI sees nothing. A job killed by a restart
  stays `running` forever, so `is_stale()` reports it as failed after 15 minutes and
  lets the owner start another. Credits are spent one unit at a time, after the work
  succeeds. TestClient runs BackgroundTasks inline, so in tests a POST returns with the
  job already finished.
- **Never write `User.credits_balance` directly.** All credit changes go through
  `apply_credit_delta()` (`backend/app/services/credits.py`): an atomic conditional
  `UPDATE` plus a `CreditTransaction` row in the same transaction, so the balance can't go
  negative under concurrent requests and the ledger always sums to it. A plain
  `user.credits_balance -= 1` reintroduces a race (12 parallel requests spent a 3-credit
  balance) and leaves the admin panel's ledger inconsistent.
- The pytest suite runs on SQLite by default; run it against Postgres with
  `TEST_DATABASE_URL=postgresql://... pytest` (see `backend/README.md`) before shipping a
  schema/migration/billing change — that mode also enables the Postgres-only concurrency
  tests. The app seeds the default pack catalog on startup when the `product` table is
  empty, so a `create_all` dev DB isn't missing its packs.
- **`docs/DATABASE.md` is the runbook** for creating, moving or rebuilding the database.
  `alembic upgrade head` on an empty Postgres builds the whole schema; `alembic check`
  then proves the live tables match `app/models.py` and must stay clean — if it reports
  drift, the migrations and the models have diverged.
- SQLite (dev + the whole pytest suite) does **not** enforce enum labels;
  Postgres (production) does. SQLAlchemy stores an `Enum` column by member
  *name*, so a Python enum whose name differs from its value (e.g.
  `CheckStatus.pass_ = "pass"`) needs the Postgres type's label to be the
  **name** (`pass_`) — the initial migration got this wrong and every audit on
  Render silently saved a score with zero checks until migration `0007`. When
  adding or changing an enum, verify against a real Postgres (throwaway
  `docker run postgres:16`, `DATABASE_URL=... alembic upgrade head`, then
  exercise the insert) — the test suite alone won't catch it.
- Any `useSearchParams()` usage in a page component needs a `<Suspense>`
  boundary around it, or `next build` fails with "should be wrapped in a
  suspense boundary". This doesn't show up in `npm run dev` — only a
  production build catches it, so run `npm run build` before considering
  frontend work done.
