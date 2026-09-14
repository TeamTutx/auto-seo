import type {
  Alert,
  AltTextSuggestion,
  AppliedFix,
  Audit,
  AuditDetail,
  CompetitorResult,
  GAPageMetrics,
  GoogleAuthorizeResponse,
  GoogleConnectionStatus,
  GSCIndexStatus,
  GSCQueryRow,
  KeywordOpportunity,
  KeywordRank,
  MetaDescriptionSuggestion,
  Opportunity,
  OpportunityType,
  Page,
  RankingActionPlan,
  Site,
  SiteHealth,
  SiteVerificationResult,
  TextSuggestion,
  TitleTagSuggestion,
  User,
  VerificationMethod,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "signal_token";

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
};
