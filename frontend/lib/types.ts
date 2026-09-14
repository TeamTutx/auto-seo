export type PlanTier = "free" | "pro" | "agency";
export type CheckStatus = "pass" | "warning" | "fail";
export type VerificationMethod = "dns_txt" | "meta_tag" | "file_upload";

export interface User {
  id: number;
  email: string;
  plan: PlanTier;
  credits_balance: number;
  created_at: string;
}

export interface Site {
  id: number;
  domain: string;
  verified: boolean;
  verification_method: VerificationMethod | null;
  verification_token: string;
  created_at: string;
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
