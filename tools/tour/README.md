# Product tour capture

Regenerates the screenshots on [`/how-it-works`](../../frontend/app/how-it-works).

**Re-run this whenever the dashboard UI changes.** The page's credibility comes
from the images being the real product, and nothing in CI can notice when they
stop being that — a stale screenshot looks exactly like a fresh one.

Everything is invented and self-contained: a demo customer site built to have SEO
problems worth showing, its own SQLite database, and a stubbed AI vendor. No real
customer data appears in a public page, and no OpenAI or SerpApi call is made to
fill a screenshot. The audits, the scoring, the change compiler and the write
targets are the real implementations — a tour of mocked output would be a drawing
of the product rather than the product.

```sh
# 1. the site being audited (deliberately flawed; also answers WordPress's REST API)
backend/.venv/bin/python tools/tour/demo_site.py &

# 2. invented account, site, ranks, keyword ideas and visibility readings
cd backend && DATABASE_URL="sqlite:///../tour.db" .venv/bin/python ../tools/tour/seed.py

# 3. the real API, with the AI vendor stubbed
DATABASE_URL="sqlite:///../tour.db" .venv/bin/python ../tools/tour/api.py &

# 4. the frontend, pointed at it (frontend/.env.local already uses :8000)
npm run dev --prefix frontend &

# 5. audit the demo page, then set up the states the tour shows
#    (compile a fix and leave it proposed; apply another so the receipt shows)

# 6. capture
cd tools/tour && npm install && TOUR_OUT=../../frontend/public/tour npm run capture
```

Playwright lives in this directory's own `package.json`, not the frontend's:
Render runs `npm ci` in `frontend/` on every static build and would download a
browser each time for a script no deploy ever runs.

Captured at `deviceScaleFactor: 1.5` — sharp at the width the page displays them
and roughly half the bytes of 2x.
