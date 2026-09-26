import type {
  AdminProduct,
  AdminStats,
  AdminUserDetail,
  AdminUserList,
  Alert,
  AltTextSuggestion,
  AppliedFix,
  ApplyChangesResult,
  Audit,
  AuditDetail,
  BillingSummary,
  CompetitorResult,
  GAPageMetrics,
  GSCIndexStatus,
  GSCQueryRow,
  GeneratedResult,
  GoogleAuthorizeResponse,
  GoogleConnectionStatus,
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
  ProposedChange,
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
  VisibilityAdvice,
  VisibilityReport,
  WriteTarget,
  WriteTargetConnect,
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

/** Called after any request that may have spent a credit, so the balance in the
 *  sidebar updates without a reload. AuthProvider registers the handler; keeping
 *  it here means a metered call refreshes the balance wherever it's made from,
 *  rather than every caller having to remember. */
let onCreditsSpent: (() => void) | null = null;

export function setCreditsListener(handler: (() => void) | null) {
  onCreditsSpent = handler;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { metered?: boolean } = {},
): Promise<T> {
  const { metered, ...init } = options;
  const token = getToken();
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  if (init.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });

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
  // Only on success: a 402 or a vendor failure means nothing was charged.
  if (metered) onCreditsSpent?.();
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
      metered: true,
      body: JSON.stringify({
        keyword,
        ...(locationCode !== undefined ? { location_code: locationCode } : {}),
        ...(device !== undefined ? { device } : {}),
      }),
    }),
  recheckKeywords: (pageId: number) =>
    request<KeywordRank[]>(`/pages/${pageId}/keywords/recheck`, { method: "POST", metered: true }),
  deleteKeyword: (pageId: number, keyword: string) =>
    request<void>(`/pages/${pageId}/keywords?keyword=${encodeURIComponent(keyword)}`, { method: "DELETE" }),
  keywordHistory: (pageId: number, keyword: string) =>
    request<KeywordRank[]>(`/pages/${pageId}/keywords/history?keyword=${encodeURIComponent(keyword)}`),
  getCompetitors: (pageId: number, keyword: string, locationCode?: number, device?: string) =>
    request<CompetitorResult[]>(`/pages/${pageId}/keywords/competitors`, {
      method: "POST",
      metered: true,
      body: JSON.stringify({
        keyword,
        ...(locationCode !== undefined ? { location_code: locationCode } : {}),
        ...(device !== undefined ? { device } : {}),
      }),
    }),

  suggestMetaDescription: (pageId: number) =>
    request<MetaDescriptionSuggestion>(`/pages/${pageId}/suggestions/meta-description`, { method: "POST", metered: true }),
  suggestTitleTag: (pageId: number) =>
    request<TitleTagSuggestion>(`/pages/${pageId}/suggestions/title-tag`, { method: "POST", metered: true }),
  suggestHeading: (pageId: number) =>
    request<TextSuggestion>(`/pages/${pageId}/suggestions/heading`, { method: "POST", metered: true }),
  suggestReadability: (pageId: number) =>
    request<TextSuggestion>(`/pages/${pageId}/suggestions/readability`, { method: "POST", metered: true }),
  suggestInternalLinks: (pageId: number) =>
    request<TextSuggestion>(`/pages/${pageId}/suggestions/internal-links`, { method: "POST", metered: true }),
  suggestAltText: (pageId: number) =>
    request<AltTextSuggestion[]>(`/pages/${pageId}/suggestions/alt-text`, { method: "POST", metered: true }),

  listAlerts: () => request<Alert[]>("/alerts"),
  markAlertRead: (id: number) => request<Alert>(`/alerts/${id}/read`, { method: "POST" }),

  // crawl, keyword discovery, visibility - all three start a background run and
  // return a job the caller polls with siteJobs()
  siteJobs: (siteId: number) => request<SiteJobs>(`/sites/${siteId}/jobs`),
  searchPresence: (siteId: number) => request<SearchPresence>(`/sites/${siteId}/presence`),
  startCrawl: (siteId: number) => request<SiteJob>(`/sites/${siteId}/crawl`, { method: "POST" }),
  indexSummary: (siteId: number) => request<IndexSummary>(`/sites/${siteId}/index-summary`),
  checkPageIndex: (pageId: number) => request<Page>(`/pages/${pageId}/index-check`, { method: "POST", metered: true }),

  discoverKeywords: (siteId: number) =>
    request<SiteJob>(`/sites/${siteId}/keywords/discover`, { method: "POST" }),
  keywordIdeas: (siteId: number) => request<KeywordIdea[]>(`/sites/${siteId}/keywords/ideas`),
  /** Add a keyword by hand, targeted straight away. Free - nothing is looked up
   *  until a visibility check runs. */
  addSiteKeyword: (siteId: number, keyword: string) =>
    request<KeywordIdea>(`/sites/${siteId}/keywords`, {
      method: "POST",
      body: JSON.stringify({ keyword }),
    }),
  pageGeneratedResults: (pageId: number) => request<GeneratedResult[]>(`/pages/${pageId}/generated`),
  targetKeywords: (siteId: number, ids: number[], targeted: boolean) =>
    request<KeywordIdea[]>(`/sites/${siteId}/keywords/target`, {
      method: "POST",
      body: JSON.stringify({ ids, targeted }),
    }),
  deleteKeywordIdea: (siteId: number, ideaId: number) =>
    request<void>(`/sites/${siteId}/keywords/ideas/${ideaId}`, { method: "DELETE" }),

  /** No keyword checks every targeted keyword; a keyword checks just that one.
   *  Not flagged `metered` even though it spends credits: the job charges as it
   *  runs, so the balance is refreshed when the job finishes, not when it starts. */
  startVisibilityCheck: (siteId: number, keyword?: string) =>
    request<SiteJob>(`/sites/${siteId}/visibility/check`, {
      method: "POST",
      body: JSON.stringify(keyword ? { keyword } : {}),
    }),
  visibilityReport: (siteId: number) => request<VisibilityReport>(`/sites/${siteId}/visibility`),
  suggestForKeyword: (siteId: number, keyword: string) =>
    request<VisibilityAdvice>(`/sites/${siteId}/visibility/suggest`, {
      method: "POST",
      metered: true,
      body: JSON.stringify({ keyword }),
    }),

  getOpportunities: (siteId: number) => request<Opportunity[]>(`/sites/${siteId}/opportunities`),
  getSiteHealth: (siteId: number) => request<SiteHealth>(`/sites/${siteId}/health`),

  getKeywordOpportunities: (pageId: number, keyword: string, locationCode?: number, device?: string) =>
    request<KeywordOpportunity[]>(`/pages/${pageId}/keywords/opportunities`, {
      method: "POST",
      metered: true,
      body: JSON.stringify({
        keyword,
        ...(locationCode !== undefined ? { location_code: locationCode } : {}),
        ...(device !== undefined ? { device } : {}),
      }),
    }),

  getRankingActionPlan: (pageId: number, keyword: string, locationCode?: number, device?: string) =>
    request<RankingActionPlan>(`/pages/${pageId}/keywords/action-plan`, {
      method: "POST",
      metered: true,
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
  // --- applying fixes (Phase K in plan.md) ---

  /** Null when the site has no connection - the normal state, not an error. */
  getWriteTarget: (siteId: number) => request<WriteTarget | null>(`/sites/${siteId}/write-target`),
  connectWriteTarget: (siteId: number, body: WriteTargetConnect) =>
    request<WriteTarget>(`/sites/${siteId}/write-target`, { method: "PUT", body: JSON.stringify(body) }),
  testWriteTarget: (siteId: number) =>
    request<WriteTarget>(`/sites/${siteId}/write-target/test`, { method: "POST" }),
  disconnectWriteTarget: (siteId: number) =>
    request<void>(`/sites/${siteId}/write-target`, { method: "DELETE" }),

  pageChanges: (pageId: number) => request<ProposedChange[]>(`/pages/${pageId}/changes`),
  siteChanges: (siteId: number) => request<ProposedChange[]>(`/sites/${siteId}/changes`),
  /** Metered where a model runs. The deterministic fields (canonical, robots)
   *  cost nothing, and the API is the one that decides - so this always refreshes
   *  the balance and the sidebar simply shows the same number when nothing moved. */
  compileChange: (pageId: number, field: string) =>
    request<ProposedChange[]>(`/pages/${pageId}/changes/compile`, {
      method: "POST",
      metered: true,
      body: JSON.stringify({ field }),
    }),
  /** Free: the credit paid for the compile. */
  applyChanges: (pageId: number, ids: number[]) =>
    request<ApplyChangesResult>(`/pages/${pageId}/changes/apply`, {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
  revertChanges: (pageId: number, ids: number[]) =>
    request<ApplyChangesResult>(`/pages/${pageId}/changes/revert`, {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
  discardChange: (pageId: number, changeId: number) =>
    request<void>(`/pages/${pageId}/changes/${changeId}`, { method: "DELETE" }),

};
