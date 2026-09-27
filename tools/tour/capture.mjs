/**
 * Capture the screenshots the product tour uses.
 *
 * Real Chrome against the real dashboard, logged in as the seeded demo account -
 * so every image is the product, not a drawing of it. Committed rather than run
 * once, because a screenshot goes stale silently: when the UI moves, re-running
 * this is the whole cost of keeping /how-it-works honest.
 *
 *   python tools/tour/demo_site.py &
 *   DATABASE_URL=sqlite:///tour.db python tools/tour/seed.py
 *   DATABASE_URL=sqlite:///tour.db python tools/tour/api.py &
 *   npm run dev --prefix frontend &
 *   node tools/tour/capture.mjs
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const APP = process.env.TOUR_APP ?? "http://localhost:3000";
const API = process.env.TOUR_API ?? "http://localhost:8000";
const OUT = process.env.TOUR_OUT ?? "frontend/public/tour";
const EMAIL = "tour@fernandfox.example";
const PASSWORD = "tour-demo-account";

const SHOTS = [
  { name: "site-overview", path: "/dashboard/site?id=1", wait: ".score-panel" },
  { name: "page-audit", path: "/dashboard/page?site=1&id=1", wait: ".check-card" },
  { name: "keywords", path: "/dashboard/site/keywords?id=1", wait: "body" },
  { name: "visibility", path: "/dashboard/site/visibility?id=1", wait: "body" },
  { name: "opportunities", path: "/dashboard/site/opportunities?id=1", wait: "body" },
  { name: "billing", path: "/dashboard/billing", wait: "body" },
];

async function token() {
  const body = new URLSearchParams({ username: EMAIL, password: PASSWORD });
  const res = await fetch(`${API}/auth/login`, { method: "POST", body });
  if (!res.ok) throw new Error(`login failed: ${res.status} - is the tour API running on ${API}?`);
  return (await res.json()).access_token;
}

const jwt = await token();
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ channel: "chrome" });
const context = await browser.newContext({
  viewport: { width: 1360, height: 900 },
  deviceScaleFactor: 1.5,
  colorScheme: "dark",
});
// Seed the session before any page script runs, so the dashboard never flashes
// its logged-out redirect into a screenshot.
await context.addInitScript(([key, value]) => {
  try { window.localStorage.setItem(key, value); } catch {}
}, ["signal_token", jwt]);

const page = await context.newPage();

for (const shot of SHOTS) {
  await page.goto(`${APP}${shot.path}`, { waitUntil: "networkidle" });
  await page.waitForSelector(shot.wait, { timeout: 15000 }).catch(() => {});
  // Background jobs poll and credit counts tick; a beat of quiet avoids catching
  // a spinner mid-frame.
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${OUT}/${shot.name}.png`, fullPage: false });
  console.log(`captured ${shot.name}`);
}

// The two that need a card opened rather than a page loaded.
await page.goto(`${APP}/dashboard/page?site=1&id=1`, { waitUntil: "networkidle" });
await page.waitForSelector(".check-card", { timeout: 15000 });
await page.waitForTimeout(1500);

const metaCard = page.locator(".check-card", { hasText: "Meta Description" }).first();
await metaCard.scrollIntoViewIfNeeded();
await page.waitForTimeout(400);
await metaCard.screenshot({ path: `${OUT}/fix-diff.png` });
console.log("captured fix-diff");

const altCard = page.locator(".check-card", { hasText: "Image Alt Text" }).first();
await altCard.scrollIntoViewIfNeeded();
await page.waitForTimeout(400);
await altCard.screenshot({ path: `${OUT}/fix-applied.png` });
console.log("captured fix-applied");

await page.goto(`${APP}/dashboard/site?id=1`, { waitUntil: "networkidle" });
await page.waitForTimeout(1200);
const connect = page.locator(".panel", { hasText: "Applying fixes" }).first();
await connect.scrollIntoViewIfNeeded();
await page.waitForTimeout(400);
await connect.screenshot({ path: `${OUT}/connect.png` });
console.log("captured connect");

await browser.close();
console.log(`\ndone - ${OUT}`);
