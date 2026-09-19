import type { Pricing } from "./types";

// Fallback for the landing page when the API can't be reached (build time,
// an outage), so visitors always see sane prices. It mirrors the ladder the
// 0009 migration seeds and ACCOUNT_LIMITS in backend/app/models.py; the *live*
// packs come from GET /pricing (created and priced in /admin/pricing), and
// there can be any number of them.
export const DEFAULT_PRICING: Pricing = {
  billing_enabled: false,
  signup_credits: 3,
  limits: { max_sites: 5, max_pages_per_site: 50, max_keywords_per_page: 25 },
  credit_packs: [
    {
      key: "credits_10",
      name: "10 credits",
      price_cents: 200,
      credits: 10,
      description: "Enough to try a few rank checks",
      badge: null,
      price_per_credit_cents: 20,
      purchasable: false,
    },
    {
      key: "credits_50",
      name: "50 credits",
      price_cents: 500,
      credits: 50,
      description: "For a site you're actively working on",
      badge: "Best value",
      price_per_credit_cents: 10,
      purchasable: false,
    },
    {
      key: "credits_200",
      name: "200 credits",
      price_cents: 1500,
      credits: 200,
      description: "For agencies and multiple sites",
      badge: null,
      price_per_credit_cents: 7.5,
      purchasable: false,
    },
  ],
};
