# Signal — Self-Serve SEO Platform

A website that lets users run SEO audits, track keyword rankings, and get
AI-assisted fixes for their own web pages — without hiring an agency.

- Full requirements: [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md)
- UI mockup / design reference: [`frontend/seo-dashboard-mockup.html`](frontend/seo-dashboard-mockup.html)
- Backend details: [`backend/README.md`](backend/README.md)
- Frontend details: [`frontend/README.md`](frontend/README.md)

## Features

**Sites & pages**
- Add, edit, and delete sites and pages; domain input is validated and
  normalized (rejects things like `"zepto"` with no TLD).
- Domain ownership verification — DNS TXT record, meta tag, or hosted file
  (same three options Google Search Console offers).

**On-page SEO audits** (free, no external API cost)
- Checks: title tag, meta description, heading structure, image alt text,
  internal/external links, content length, keyword density, readability
  (Flesch score), canonical tag, robots meta, structured data (schema.org).
- 0–100 score per page, recalculated on every scan.
- Manual rescan, throttled to 1×/day on the free plan; unlimited on
  Pro/Agency.

**Keyword rank tracking**
- Track keywords per page with a location/device picker (defaults to
  India; also supports US/UK/Canada/Australia, desktop or mobile).
- Rank-history chart per keyword.
- Competitor comparison — top organic results for a keyword, your own
  domain excluded.
- "Recheck rankings now" to refresh every tracked keyword on a page at once.
- Backed by SerpApi or DataForSEO — swappable via one config value, no
  code changes.

**AI-generated suggestions**
- One-click meta description and title tag rewrites, generated from the
  page's actual content and target keyword.
- Backed by OpenAI or Anthropic — swappable via one config value.

**Scheduled audits + alerts** (Pro/Agency)
- Daily automated re-audit of every page on a paid plan.
- In-app alerts when a page's score drops ≥10 points or a check starts
  newly failing — shown as a badge in the dashboard sidebar.

**Accounts & plans**
- Email/password auth (JWT).
- Free / Pro / Agency plans with enforced limits (sites, pages per site,
  tracked keywords per page).
- Credit system metering paid actions (rank checks, AI suggestions,
  competitor lookups) — ready for Stripe to plug into later.

**Google Search Console / Analytics** (needs a one-time Google Cloud OAuth
setup — see the API keys table below)
- Connect a Google account (Settings page) and pick which Search Console
  property and GA4 property belongs to each site.
- Real search queries, clicks, impressions, and average position per page —
  a different, complementary signal to the SerpApi/DataForSEO rank checks
  above: those tell you where you rank for a keyword you specify, this
  tells you what people are *actually* searching that leads to clicks,
  including queries you never thought to track.
- Indexing status per page (Search Console's URL Inspection) — the real
  answer to "why does this page have zero rank" when it's simply not been
  crawled yet, as opposed to a ranking problem.
- Real traffic per page (sessions, pageviews, bounce rate, engagement).

**Not yet built:** Stripe billing (deliberately deferred), keyword
search-volume/difficulty data (needs a funded keyword-data API), email
delivery for alerts (needs a Resend/SendGrid key), AI content briefs, and
team/agency multi-user seats. Details and reasoning for each are in
[`backend/README.md`](backend/README.md#known-gaps).

## Stack
- **Backend:** Python, FastAPI, SQLModel, Celery + Redis (scheduled audits)
- **Frontend:** Next.js (App Router), TypeScript
- **DB:** SQLite for local dev, PostgreSQL via `DATABASE_URL` for anything real
- **External services:** SerpApi/DataForSEO (rank data), OpenAI/Anthropic
  (AI suggestions), Google Search Console/Analytics (real search + traffic
  data, OAuth) — Stripe planned, not yet integrated

## How to run

### Prerequisites
- Python 3.9+
- Node.js ≥ 18.17 (`node --version` — if it's older, the frontend won't
  start; see [`frontend/README.md`](frontend/README.md) for a Homebrew fix)
- Redis — only needed for scheduled audits/alerts; everything else runs
  without it

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and fill in whichever API keys you have (see the table below —
none are required just to get the server running; features that need a
missing key return a clean error instead of crashing).

```bash
uvicorn app.main:app --reload
```

API is now at `http://localhost:8000` (interactive docs at `/docs`).
SQLite tables are created automatically on first run.

### 2. Frontend

In a second terminal:

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

The app is now at `http://localhost:3000` — a public landing page explaining
the product, with "Get started free" leading to registration. The dashboard
itself lives at `/dashboard` once you're signed in; the local database
starts empty.

### 3. (Optional) Scheduled audits — Redis + Celery

Only needed if you want the daily Pro/Agency audit + alert job to actually
run. Skip this if you're just exploring the app.

```bash
redis-server                                            # or: brew services start redis
cd backend && source .venv/bin/activate
celery -A app.workers.celery_app worker --loglevel=info  # in one terminal
celery -A app.workers.celery_app beat --loglevel=info    # in another
```

### API keys

None of these are required to start the app — each just unlocks one
feature area. Add them to `backend/.env` as you get them.

| Key(s) | Unlocks | Get it from |
|---|---|---|
| `SERPAPI_KEY` (default) or `DATAFORSEO_LOGIN`/`DATAFORSEO_PASSWORD` | Keyword rank checks, competitor comparison | [serpapi.com](https://serpapi.com) (100 free searches/mo) or [dataforseo.com](https://dataforseo.com) |
| `OPENAI_API_KEY` (default) or `ANTHROPIC_API_KEY` | AI meta description/title suggestions | [platform.openai.com](https://platform.openai.com) or [console.anthropic.com](https://console.anthropic.com) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Connect Google Search Console / Analytics | [console.cloud.google.com](https://console.cloud.google.com) — an OAuth client, not a static key; see the "Google Search Console / Analytics integration" section in [`backend/README.md`](backend/README.md) for the exact setup steps |

Switch which vendor is active with `RANK_PROVIDER` (`serpapi` /
`dataforseo`) and `AI_PROVIDER` (`openai` / `anthropic`) in `.env` — no
code changes needed either way.

## Project structure

```
backend/    FastAPI app — see backend/README.md for the full endpoint/module breakdown
frontend/   Next.js dashboard — see frontend/README.md for the component breakdown
docs/       Product & technical requirements (docs/REQUIREMENTS.md)
```
