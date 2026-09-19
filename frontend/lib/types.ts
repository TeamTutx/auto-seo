export type PlanTier = "free" | "pro" | "agency";
export type CheckStatus = "pass" | "warning" | "fail";
export type VerificationMethod = "dns_txt" | "meta_tag" | "file_upload";

export interface User {
  id: number;
  email: string;
  plan: PlanTier;
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

export interface Page {
  id: number;
  site_id: number;
  url: string;
  target_keyword: string | null;
  created_at: string;
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

export interface PricingPlan {
  key: PlanTier;
  name: string;
  price_cents: number;
  interval: string | null;
  description: string | null;
  limits: PlanLimits;
  product_key: string | null;
  purchasable: boolean;
}

export interface PricingCreditPack {
  key: string;
  name: string;
  price_cents: number;
  credits: number;
  description: string | null;
  purchasable: boolean;
}

export interface Pricing {
  billing_enabled: boolean;
  plans: PricingPlan[];
  credit_packs: PricingCreditPack[];
}

export interface BillingPayment {
  id: number;
  amount_cents: number;
  kind: string;
  plan: string | null;
  credits_granted: number;
  paid_at: string;
}

export interface BillingSummary {
  plan: PlanTier;
  credits_balance: number;
  billing_enabled: boolean;
  has_subscription: boolean;
  can_manage_billing: boolean;
  payments: BillingPayment[];
}

// --- admin ---

export interface AdminUserRow {
  id: number;
  email: string;
  plan: PlanTier;
  credits_balance: number;
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
  plan: string | null;
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
  plan: PlanTier;
  credits_balance: number;
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

export interface AdminStats {
  total_users: number;
  signups_7d: number;
  signups_30d: number;
  users_by_plan: Record<string, number>;
  paying_users: number;
  revenue_all_cents: number;
  revenue_30d_cents: number;
  estimated_mrr_cents: number;
  credits_outstanding: number;
  credits_spent_30d: number;
  recent_signups: AdminUserRow[];
  recent_actions: AdminAuditRow[];
}

export interface AdminProduct {
  id: number;
  key: string;
  name: string;
  kind: "subscription" | "credit_pack";
  price_cents: number;
  interval: string | null;
  plan: string | null;
  credits: number;
  dodo_product_id: string | null;
  description: string | null;
  active: boolean;
  sort_order: number;
  updated_at: string;
}

export interface ProductVerifyResult {
  ok: boolean;
  message: string;
  dodo_price_cents: number | null;
  dodo_currency: string | null;
}
