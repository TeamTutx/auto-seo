# Signal — working notes for Claude Code

Self-serve SEO platform. FastAPI backend (`backend/`) + Next.js App Router
frontend (`frontend/`). Full feature/roadmap history lives in `plan.md` —
read that for what's built, what's deliberately deferred, and why.

## Landing page parity

`frontend/app/page.tsx` (the public `/` route) is a marketing page that
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
- Plan limits changed (`backend/app/models.py` `PLAN_LIMITS`) → update the
  numbers in the Plans section of `page.tsx` (search for the comment above
  `lp-plans-grid` that points back at `PLAN_LIMITS`).
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

- `/` — public landing page (`app/page.tsx`), not auth-gated.
- `/login` — single page, handles both sign-in and sign-up (`?mode=register`
  defaults the toggle to registration). Redirects to `/dashboard` if already
  authenticated.
- `/dashboard/*` — the actual product (sites, pages, settings), gated by
  `app/dashboard/layout.tsx` (redirects to `/login` if unauthenticated).
  This used to be a route group living at `/` before the landing page
  existed — if you ever run across old links to `/sites/...` or `/settings`
  (missing the `/dashboard` prefix), they're stale and need fixing.

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
- Any `useSearchParams()` usage in a page component needs a `<Suspense>`
  boundary around it, or `next build` fails with "should be wrapped in a
  suspense boundary". This doesn't show up in `npm run dev` — only a
  production build catches it, so run `npm run build` before considering
  frontend work done.
