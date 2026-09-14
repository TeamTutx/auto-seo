import type { Audit, AuditDetail, KeywordRank, MetaDescriptionSuggestion, Page, Site, User } from "./types";

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
  updateSite: (id: number, domain: string) =>
    request<Site>(`/sites/${id}`, { method: "PATCH", body: JSON.stringify({ domain }) }),
  deleteSite: (id: number) => request<void>(`/sites/${id}`, { method: "DELETE" }),

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
  addKeyword: (pageId: number, keyword: string) =>
    request<KeywordRank>(`/pages/${pageId}/keywords`, { method: "POST", body: JSON.stringify({ keyword }) }),
  recheckKeywords: (pageId: number) =>
    request<KeywordRank[]>(`/pages/${pageId}/keywords/recheck`, { method: "POST" }),

  suggestMetaDescription: (pageId: number) =>
    request<MetaDescriptionSuggestion>(`/pages/${pageId}/suggestions/meta-description`, { method: "POST" }),
};
