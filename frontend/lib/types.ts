export type CheckStatus = "pass" | "warning" | "fail";
export type VerificationMethod = "dns_txt" | "meta_tag" | "file_upload";

export interface User {
  id: number;
  email: string;
  credits_balance: number;
  created_at: string;
  is_admin: boolean;
}

export interface Site {
  id: number;
  domain: string;
  verified: boolean;
  verification_method: VerificationMethod | null;
  verification_token: string;
  created_at: string;
  gsc_property: string | null;
  ga_property_id: string | null;
}

export type IndexStatus = "indexed" | "not_indexed" | "unknown";

export interface Page {
  id: number;
  site_id: number;
  url: string;
  target_keyword: string | null;
  created_at: string;
  discovered_via: "manual" | "sitemap" | "link";
  index_status: IndexStatus | null;
  index_detail: string | null;
  /** "gsc" = Google told us directly; "serp" = inferred from a site: search. */
  index_source: "gsc" | "serp" | null;
  index_checked_at: string | null;
}

export interface Check {
  check_type: string;
  status: CheckStatus;
  message: string;
  suggested_fix: string | null;
}

export interface Audit {
  id: number;
  page_id: number;
  score: number | null;
  extracted_title: string | null;
  word_count: number | null;
  created_at: string;
}

export interface AuditDetail extends Audit {
  checks: Check[];
}

export interface KeywordRank {
  id: number;
  page_id: number;
  keyword: string;
  rank_position: number | null;
  provider: string | null;
  location_code: number;
  language_code: string;
  device: string;
  checked_at: string;
}

export interface MetaDescriptionSuggestion {
  suggestion: string;
}

export interface TitleTagSuggestion {
  suggestion: string;
}

// Shape shared by the heading/readability/internal-linking suggestion endpoints.
export interface TextSuggestion {
  suggestion: string;
}

export interface AltTextSuggestion {
  src: string;
  suggested_alt: string;
}

export interface KeywordOpportunity {
  keyword: string;
  reason: string;
}

export interface SiteVerificationResult {
  verified: boolean;
  message: string;
}

export interface CompetitorResult {
  position: number;
  title: string;
  domain: string;
  url: string;
}

export interface LocationOption {
  code: number;
  label: string;
}

export const LOCATION_OPTIONS: LocationOption[] = [
  { code: 2356, label: "India" },
  { code: 2840, label: "United States" },
  { code: 2826, label: "United Kingdom" },
  { code: 2124, label: "Canada" },
  { code: 2036, label: "Australia" },
];

export type AlertType = "score_drop" | "new_fail" | "fix_verified";

export interface Alert {
  id: number;
  page_id: number;
  site_id: number;
  alert_type: AlertType;
  message: string;
  read: boolean;
  created_at: string;
}

export type OpportunityType =
  | "audit_fail"
  | "audit_warning"
  | "keyword_not_found"
  | "keyword_low_rank"
  | "keyword_rank_drop";

export type OpportunitySeverity = "high" | "medium" | "low";

export interface Opportunity {
  type: OpportunityType;
  severity: OpportunitySeverity;
  page_id: number;
  page_url: string;
  title: string;
  detail: string;
  suggested_fix: string | null;
  check_type: string | null;
  keyword: string | null;
  applied: boolean;
}

export interface AppliedFix {
  id: number;
  page_id: number;
  type: OpportunityType;
  check_type: string | null;
  keyword: string | null;
  applied_at: string;
  resolved: boolean;
  resolved_at: string | null;
}

export interface RankingActionPlan {
  plan: string;
}

export interface ScoreTrendPoint {
  date: string;
  score: number;
}

export interface ScoreMovement {
  page_id: number;
  page_url: string;
  previous_score: number;
  new_score: number;
  delta: number;
}

export interface KeywordMovement {
  page_id: number;
  page_url: string;
  keyword: string;
  previous_rank: number | null;
  new_rank: number | null;
  delta: number;
}

export interface SiteHealth {
  score_trend: ScoreTrendPoint[];
  score_wins: ScoreMovement[];
  score_losses: ScoreMovement[];
  keyword_wins: KeywordMovement[];
  keyword_losses: KeywordMovement[];
  top_opportunities: Opportunity[];
}

export interface GoogleAuthorizeResponse {
  authorize_url: string;
}

export interface GAPropertyOption {
  property_id: string;
  display_name: string;
}

export interface GoogleConnectionStatus {
  connected: boolean;
  connected_at: string | null;
  gsc_properties: string[];
  ga_properties: GAPropertyOption[];
}

export interface GSCQueryRow {
  query: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

export interface GSCIndexStatus {
  indexed: boolean;
  verdict: string;
  coverage_state: string;
  last_crawl_time: string | null;
}

export interface GAPageMetrics {
  sessions: number;
  pageviews: number;
  bounce_rate: number;
  avg_session_duration: number;
}

// --- pricing / billing ---

export interface PlanLimits {
  max_sites: number | null; // null = unlimited
  max_pages_per_site: number | null;
  max_keywords_per_page: number | null;
}

export interface PricingCreditPack {
  key: string;
  name: string;
  price_cents: number;
  credits: number;
  description: string | null;
  badge: string | null;
  price_per_credit_cents: number | null;
  purchasable: boolean;
}

/** Signal sells credits and nothing else: no tiers, one set of limits. */
export interface Pricing {
  billing_enabled: boolean;
  signup_credits: number;
  limits: PlanLimits;
  credit_packs: PricingCreditPack[];
}

export interface BillingPayment {
  id: number;
  amount_cents: number;
  kind: string;
  product_key: string | null;
  credits_granted: number;
  paid_at: string;
}

export interface BillingSummary {
  credits_balance: number;
  credits_purchased: number;
  billing_enabled: boolean;
  can_manage_billing: boolean;
  packs: PricingCreditPack[];
  payments: BillingPayment[];
}

// --- crawl, keyword discovery, visibility ---

export type JobStatus = "queued" | "running" | "done" | "failed";
export type JobKind = "crawl" | "keywords" | "visibility";

export interface SiteJob {
  id: number;
  kind: JobKind;
  status: JobStatus;
  progress: number;
  total: number;
  message: string | null;
  error: string | null;
  credits_spent: number;
  created_at: string;
  finished_at: string | null;
}

export type SiteJobs = Record<JobKind, SiteJob | null>;

export interface IndexSummary {
  total_pages: number;
  indexed: number;
  not_indexed: number;
  unchecked: number;
  source: "gsc" | "serp" | null;
}

export interface KeywordIdea {
  id: number;
  keyword: string;
  /** "gsc" ideas carry real measured numbers; "ai" and "serp" are suggestions. */
  source: "gsc" | "ai" | "serp";
  rationale: string | null;
  impressions: number | null;
  clicks: number | null;
  position: number | null;
  targeted: boolean;
}

export type VisibilityEngine = "google" | "google_ai_overview" | "chatgpt";

export interface VisibilityEngineResult {
  engine: VisibilityEngine;
  present: boolean;
  position: number | null;
  detail: string | null;
  checked_at: string;
}

export interface VisibilityKeyword {
  keyword: string;
  engines: VisibilityEngineResult[];
}

export interface VisibilityReport {
  checked_at: string | null;
  targeted_keywords: number;
  google_visible: number;
  ai_overview_cited: number;
  chatgpt_mentions: number;
  keywords: VisibilityKeyword[];
}

// --- admin ---

export interface AdminUserRow {
  id: number;
  email: string;
  credits_balance: number;
  credits_purchased: number;
  created_at: string;
  sites_count: number;
  total_paid_cents: number;
  last_active_at: string | null;
  is_admin: boolean;
}

export interface AdminUserList {
  items: AdminUserRow[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminPaymentRow {
  id: number;
  amount_cents: number;
  tax_cents: number;
  kind: string;
  product_key: string | null;
  credits_granted: number;
  provider: string;
  provider_ref: string | null;
  note: string | null;
  paid_at: string;
}

export interface AdminLedgerRow {
  id: number;
  delta: number;
  balance_after: number;
  reason: string;
  ref: string | null;
  note: string | null;
  actor_email: string | null;
  created_at: string;
}

export interface AdminAuditRow {
  id: number;
  action: string;
  actor_email: string | null;
  target_user_id: number | null;
  payload: string | null;
  created_at: string;
}

export interface AdminUserDetail {
  id: number;
  email: string;
  credits_balance: number;
  credits_purchased: number;
  created_at: string;
  is_admin: boolean;
  google_connected: boolean;
  dodo_customer_id: string | null;
  dodo_subscription_id: string | null;
  total_paid_cents: number;
  last_active_at: string | null;
  sites: { id: number; domain: string; verified: boolean; pages_count: number }[];
  payments: AdminPaymentRow[];
  ledger: AdminLedgerRow[];
  audit: AdminAuditRow[];
}

export interface AdminPackSales {
  product_key: string;
  name: string;
  sales: number;
  revenue_cents: number;
  credits_granted: number;
}

export interface AdminStats {
  total_users: number;
  signups_7d: number;
  signups_30d: number;
  paying_users: number;
  revenue_all_cents: number;
  revenue_30d_cents: number;
  credits_sold_all: number;
  credits_sold_30d: number;
  credits_outstanding: number;
  credits_spent_30d: number;
  top_packs: AdminPackSales[];
  recent_signups: AdminUserRow[];
  recent_actions: AdminAuditRow[];
}

export interface AdminProduct {
  id: number;
  key: string;
  name: string;
  kind: "subscription" | "credit_pack";
  price_cents: number;
  credits: number;
  dodo_product_id: string | null;
  description: string | null;
  badge: string | null;
  active: boolean;
  sort_order: number;
  sales: number;
  updated_at: string;
}

export interface ProductVerifyResult {
  ok: boolean;
  message: string;
  dodo_price_cents: number | null;
  dodo_currency: string | null;
}
