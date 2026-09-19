import type {
  AdminProduct,
  AdminStats,
  AdminUserDetail,
  AdminUserList,
  Alert,
  AltTextSuggestion,
  AppliedFix,
  Audit,
  AuditDetail,
  BillingSummary,
  CompetitorResult,
  GAPageMetrics,
  GoogleAuthorizeResponse,
  GoogleConnectionStatus,
  GSCIndexStatus,
  GSCQueryRow,
  IndexSummary,
  KeywordIdea,
  KeywordOpportunity,
  KeywordRank,
  MetaDescriptionSuggestion,
  Opportunity,
  OpportunityType,
  Page,
  Pricing,
  ProductVerifyResult,
  RankingActionPlan,
  SearchPresence,
  Site,
  SiteHealth,
  SiteJob,
  SiteJobs,
  SiteVerificationResult,
  TextSuggestion,
  TitleTagSuggestion,
  User,
  VerificationMethod,
  VisibilityReport,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "signal_token";

/** Where "Continue with Google" sends the browser. A whole-tab navigation, not
 *  a fetch: the API redirects to Google and back, and there's no token to send
 *  until it returns one. */
export const GOOGLE_LOGIN_URL = `${API_URL}/auth/google/start`;

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      // response wasn't JSON; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  register: (email: string, password: string) =>
    request<User>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),

  login: (email: string, password: string) =>
    request<{ access_token: string; token_type: string }>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email, password }).toString(),
    }),

  me: () => request<User>("/auth/me"),

  listSites: () => request<Site[]>("/sites"),
  createSite: (domain: string) => request<Site>("/sites", { method: "POST", body: JSON.stringify({ domain }) }),
  getSite: (id: number) => request<Site>(`/sites/${id}`),
  updateSite: (id: number, data: { domain?: string; gsc_property?: string | null; ga_property_id?: string | null }) =>
    request<Site>(`/sites/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteSite: (id: number) => request<void>(`/sites/${id}`, { method: "DELETE" }),
  verifySite: (id: number, method: VerificationMethod) =>
    request<SiteVerificationResult>(`/sites/${id}/verify`, { method: "POST", body: JSON.stringify({ method }) }),

  listPages: (siteId: number) => request<Page[]>(`/sites/${siteId}/pages`),
  createPage: (siteId: number, url: string, targetKeyword?: string) =>
    request<Page>(`/sites/${siteId}/pages`, {
      method: "POST",
      body: JSON.stringify({ url, target_keyword: targetKeyword || null }),
    }),
  getPage: (id: number) => request<Page>(`/pages/${id}`),
  updatePage: (id: number, data: { url?: string; target_keyword?: string }) =>
    request<Page>(`/pages/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deletePage: (id: number) => request<void>(`/pages/${id}`, { method: "DELETE" }),

  listAudits: (pageId: number) => request<Audit[]>(`/pages/${pageId}/audits`),
  getAudit: (id: number) => request<AuditDetail>(`/audits/${id}`),
  runAudit: (pageId: number) => request<AuditDetail>(`/pages/${pageId}/audits`, { method: "POST" }),

  listKeywords: (pageId: number) => request<KeywordRank[]>(`/pages/${pageId}/keywords`),
  addKeyword: (pageId: number, keyword: string, locationCode?: number, device?: string) =>
    request<KeywordRank>(`/pages/${pageId}/keywords`, {
      method: "POST",
      body: JSON.stringify({
        keyword,
        ...(locationCode !== undefined ? { location_code: locationCode } : {}),
        ...(device !== undefined ? { device } : {}),
      }),
    }),
  recheckKeywords: (pageId: number) =>
    request<KeywordRank[]>(`/pages/${pageId}/keywords/recheck`, { method: "POST" }),
  deleteKeyword: (pageId: number, keyword: string) =>
    request<void>(`/pages/${pageId}/keywords?keyword=${encodeURIComponent(keyword)}`, { method: "DELETE" }),
  keywordHistory: (pageId: number, keyword: string) =>
    request<KeywordRank[]>(`/pages/${pageId}/keywords/history?keyword=${encodeURIComponent(keyword)}`),
  getCompetitors: (pageId: number, keyword: string, locationCode?: number, device?: string) =>
    request<CompetitorResult[]>(`/pages/${pageId}/keywords/competitors`, {
      method: "POST",
      body: JSON.stringify({
        keyword,
        ...(locationCode !== undefined ? { location_code: locationCode } : {}),
        ...(device !== undefined ? { device } : {}),
      }),
    }),

  suggestMetaDescription: (pageId: number) =>
    request<MetaDescriptionSuggestion>(`/pages/${pageId}/suggestions/meta-description`, { method: "POST" }),
  suggestTitleTag: (pageId: number) =>
    request<TitleTagSuggestion>(`/pages/${pageId}/suggestions/title-tag`, { method: "POST" }),
  suggestHeading: (pageId: number) =>
    request<TextSuggestion>(`/pages/${pageId}/suggestions/heading`, { method: "POST" }),
  suggestReadability: (pageId: number) =>
    request<TextSuggestion>(`/pages/${pageId}/suggestions/readability`, { method: "POST" }),
  suggestInternalLinks: (pageId: number) =>
    request<TextSuggestion>(`/pages/${pageId}/suggestions/internal-links`, { method: "POST" }),
  suggestAltText: (pageId: number) =>
    request<AltTextSuggestion[]>(`/pages/${pageId}/suggestions/alt-text`, { method: "POST" }),

  listAlerts: () => request<Alert[]>("/alerts"),
  markAlertRead: (id: number) => request<Alert>(`/alerts/${id}/read`, { method: "POST" }),

  // crawl, keyword discovery, visibility - all three start a background run and
  // return a job the caller polls with siteJobs()
  siteJobs: (siteId: number) => request<SiteJobs>(`/sites/${siteId}/jobs`),
  searchPresence: (siteId: number) => request<SearchPresence>(`/sites/${siteId}/presence`),
  startCrawl: (siteId: number) => request<SiteJob>(`/sites/${siteId}/crawl`, { method: "POST" }),
  indexSummary: (siteId: number) => request<IndexSummary>(`/sites/${siteId}/index-summary`),
  checkPageIndex: (pageId: number) => request<Page>(`/pages/${pageId}/index-check`, { method: "POST" }),

  discoverKeywords: (siteId: number) =>
    request<SiteJob>(`/sites/${siteId}/keywords/discover`, { method: "POST" }),
  keywordIdeas: (siteId: number) => request<KeywordIdea[]>(`/sites/${siteId}/keywords/ideas`),
  targetKeywords: (siteId: number, ids: number[], targeted: boolean) =>
    request<KeywordIdea[]>(`/sites/${siteId}/keywords/target`, {
      method: "POST",
      body: JSON.stringify({ ids, targeted }),
    }),
  deleteKeywordIdea: (siteId: number, ideaId: number) =>
    request<void>(`/sites/${siteId}/keywords/ideas/${ideaId}`, { method: "DELETE" }),

  startVisibilityCheck: (siteId: number) =>
    request<SiteJob>(`/sites/${siteId}/visibility/check`, { method: "POST" }),
  visibilityReport: (siteId: number) => request<VisibilityReport>(`/sites/${siteId}/visibility`),

  getOpportunities: (siteId: number) => request<Opportunity[]>(`/sites/${siteId}/opportunities`),
  getSiteHealth: (siteId: number) => request<SiteHealth>(`/sites/${siteId}/health`),

  getKeywordOpportunities: (pageId: number, keyword: string, locationCode?: number, device?: string) =>
    request<KeywordOpportunity[]>(`/pages/${pageId}/keywords/opportunities`, {
      method: "POST",
      body: JSON.stringify({
        keyword,
        ...(locationCode !== undefined ? { location_code: locationCode } : {}),
        ...(device !== undefined ? { device } : {}),
      }),
    }),

  getRankingActionPlan: (pageId: number, keyword: string, locationCode?: number, device?: string) =>
    request<RankingActionPlan>(`/pages/${pageId}/keywords/action-plan`, {
      method: "POST",
      body: JSON.stringify({
        keyword,
        ...(locationCode !== undefined ? { location_code: locationCode } : {}),
        ...(device !== undefined ? { device } : {}),
      }),
    }),

  applyFix: (pageId: number, type: OpportunityType, checkType?: string | null, keyword?: string | null) =>
    request<AppliedFix>(`/pages/${pageId}/opportunities/apply`, {
      method: "POST",
      body: JSON.stringify({ type, check_type: checkType ?? null, keyword: keyword ?? null }),
    }),

  connectGoogle: () => request<GoogleAuthorizeResponse>("/integrations/google/connect", { method: "POST" }),
  getGoogleStatus: () => request<GoogleConnectionStatus>("/integrations/google/status"),
  disconnectGoogle: () => request<void>("/integrations/google", { method: "DELETE" }),

  getPageSearchQueries: (pageId: number, days?: number) =>
    request<GSCQueryRow[]>(`/pages/${pageId}/gsc/queries${days ? `?days=${days}` : ""}`),
  getPageIndexStatus: (pageId: number) => request<GSCIndexStatus>(`/pages/${pageId}/gsc/index-status`),
  getPageGAMetrics: (pageId: number, days?: number) =>
    request<GAPageMetrics>(`/pages/${pageId}/ga/metrics${days ? `?days=${days}` : ""}`),

  // pricing is public (the landing page uses it); billing needs a session
  getPricing: () => request<Pricing>("/pricing"),
  // billing (signed-in user)
  getBilling: () => request<BillingSummary>("/billing"),
  startCheckout: (productKey: string) =>
    request<{ checkout_url: string }>("/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ product_key: productKey }),
    }),
  openBillingPortal: () => request<{ url: string }>("/billing/portal", { method: "POST" }),

  // admin (owner only - the API enforces it; the UI just hides the link)
  adminStats: () => request<AdminStats>("/admin/stats"),
  adminUsers: (params: {
    q?: string;
    paid?: boolean;
    sort?: string;
    order?: "asc" | "desc";
    page?: number;
    pageSize?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.paid !== undefined) qs.set("paid", String(params.paid));
    if (params.sort) qs.set("sort", params.sort);
    if (params.order) qs.set("order", params.order);
    if (params.page) qs.set("page", String(params.page));
    if (params.pageSize) qs.set("page_size", String(params.pageSize));
    return request<AdminUserList>(`/admin/users?${qs.toString()}`);
  },
  adminUser: (id: number) => request<AdminUserDetail>(`/admin/users/${id}`),
  adminAdjustCredits: (id: number, delta: number, note: string) =>
    request<AdminUserDetail>(`/admin/users/${id}/credits`, { method: "POST", body: JSON.stringify({ delta, note }) }),
  adminRecordPayment: (id: number, data: { amount_cents: number; credits: number; note: string }) =>
    request<AdminUserDetail>(`/admin/users/${id}/payments`, { method: "POST", body: JSON.stringify(data) }),
  adminProducts: () => request<AdminProduct[]>("/admin/products"),
  adminUpdateProduct: (
    id: number,
    data: Partial<
      Pick<
        AdminProduct,
        "name" | "price_cents" | "credits" | "dodo_product_id" | "description" | "badge" | "active" | "sort_order"
      >
    >
  ) => request<AdminProduct>(`/admin/products/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  adminDeleteProduct: (id: number) => request<void>(`/admin/products/${id}`, { method: "DELETE" }),
  adminReorderProducts: (ids: number[]) =>
    request<AdminProduct[]>("/admin/products/reorder", { method: "POST", body: JSON.stringify({ ids }) }),
  // Ask the Next.js server to refresh the cached landing page after a pricing
  // change. Best-effort: if it fails the page just refreshes itself within 5 minutes.
  revalidatePublicPricing: async () => {
    const token = getToken();
    if (!token) return;
    try {
      await fetch("/api/revalidate-pricing", { method: "POST", headers: { Authorization: `Bearer ${token}` } });
    } catch {
      // ignore
    }
  },
  adminCreateCreditPack: (data: {
    key: string;
    name: string;
    price_cents: number;
    credits: number;
    description?: string | null;
    badge?: string | null;
    dodo_product_id?: string | null;
  }) => request<AdminProduct>("/admin/products", { method: "POST", body: JSON.stringify(data) }),
  adminVerifyProduct: (id: number) => request<ProductVerifyResult>(`/admin/products/${id}/verify`, { method: "POST" }),
};
