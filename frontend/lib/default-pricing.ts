import type { Pricing } from "./types";

// Fallback for the landing page when the API can't be reached (build time,
// an outage), so visitors always see sane prices. It mirrors the catalog the
// 0008 migration seeds and PLAN_LIMITS in backend/app/models.py; the *live*
// values come from GET /pricing (edited in /admin/pricing).
export const DEFAULT_PRICING: Pricing = {
  billing_enabled: false,
  plans: [
    {
      key: "free",
      name: "Free",
      price_cents: 0,
      interval: null,
      description: null,
      limits: { max_sites: 1, max_pages_per_site: 5, max_keywords_per_page: 3 },
      product_key: null,
      purchasable: false,
    },
    {
      key: "pro",
      name: "Pro",
      price_cents: 2400,
      interval: "month",
      description: null,
      limits: { max_sites: 5, max_pages_per_site: 50, max_keywords_per_page: 50 },
      product_key: "pro",
      purchasable: false,
    },
    {
      key: "agency",
      name: "Agency",
      price_cents: 8900,
      interval: "month",
      description: null,
      limits: { max_sites: null, max_pages_per_site: null, max_keywords_per_page: null },
      product_key: "agency",
      purchasable: false,
    },
  ],
  credit_packs: [
    {
      key: "credits_50",
      name: "50 credits",
      price_cents: 900,
      credits: 50,
      description: "For extra rank checks and AI fixes",
      purchasable: false,
    },
  ],
};
