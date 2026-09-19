import re
from datetime import datetime
from enum import Enum
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models import AlertType, CheckStatus, OpportunityType, PlanTier, VerificationMethod

_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")


def _clean_domain(value: str) -> str:
    """Accept "example.com", "https://example.com/path", "www.example.com",
    etc. and normalize down to a bare hostname - or reject it outright. This
    is what stops a typo like "zepto" (no TLD) from being silently accepted
    and then breaking rank checks with no visible error (see keyword_rank_runner.py)."""
    value = value.strip().lower()
    netloc = urlparse(value if "//" in value else f"//{value}").netloc.split(":")[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if not netloc or not _DOMAIN_RE.match(netloc):
        raise ValueError(f'"{value}" doesn\'t look like a valid domain (expected something like example.com)')
    return netloc


# --- auth ---

class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    id: int
    email: EmailStr
    plan: PlanTier
    credits_balance: int
    created_at: datetime
    # Computed from ADMIN_EMAILS on every request, never stored - so it can't be
    # granted through the API. The UI uses it only to show the admin link; the
    # /admin/* endpoints enforce it themselves.
    is_admin: bool = False


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- sites ---

class SiteCreate(BaseModel):
    domain: str

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        return _clean_domain(v)


class SiteUpdate(BaseModel):
    domain: Optional[str] = None
    # Picked from the list GET /integrations/google/status returns for the
    # user's connected Google account - not re-validated here, same as any
    # other "pick from a server-supplied list" field in this app.
    gsc_property: Optional[str] = None
    ga_property_id: Optional[str] = None

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: Optional[str]) -> Optional[str]:
        return _clean_domain(v) if v is not None else v


class SiteRead(BaseModel):
    id: int
    domain: str
    verified: bool
    verification_method: Optional[VerificationMethod]
    verification_token: str
    created_at: datetime
    gsc_property: Optional[str]
    ga_property_id: Optional[str]


class SiteVerifyRequest(BaseModel):
    method: VerificationMethod


class SiteVerificationResult(BaseModel):
    verified: bool
    message: str


# --- pages ---

class PageCreate(BaseModel):
    url: str
    target_keyword: Optional[str] = None


class PageUpdate(BaseModel):
    url: Optional[str] = None
    target_keyword: Optional[str] = None


class PageRead(BaseModel):
    id: int
    site_id: int
    url: str
    target_keyword: Optional[str]
    created_at: datetime


# --- audits ---

class CheckRead(BaseModel):
    check_type: str
    status: CheckStatus
    message: str
    suggested_fix: Optional[str]


class AuditRead(BaseModel):
    id: int
    page_id: int
    score: Optional[int]
    extracted_title: Optional[str]
    word_count: Optional[int]
    created_at: datetime
    checks: List[CheckRead]


# --- keyword ranks ---

class KeywordRankCreate(BaseModel):
    keyword: str
    location_code: int = 2356  # India - see app/models.py KeywordRank.location_code
    language_code: str = "en"
    device: str = "desktop"


class KeywordRankRead(BaseModel):
    id: int
    page_id: int
    keyword: str
    rank_position: Optional[int]
    provider: Optional[str]
    location_code: int
    language_code: str
    device: str
    checked_at: datetime


class CompetitorsRequest(BaseModel):
    keyword: str
    location_code: int = 2356  # India - see app/models.py KeywordRank.location_code
    language_code: str = "en"
    device: str = "desktop"


class CompetitorResult(BaseModel):
    position: int
    title: str
    domain: str
    url: str


# --- AI suggestions ---

class MetaDescriptionSuggestion(BaseModel):
    suggestion: str


class TitleTagSuggestion(BaseModel):
    suggestion: str


class HeadingSuggestion(BaseModel):
    suggestion: str


class ReadabilitySuggestion(BaseModel):
    suggestion: str


class InternalLinkSuggestion(BaseModel):
    suggestion: str


class AltTextSuggestion(BaseModel):
    src: str
    suggested_alt: str


# --- keyword opportunities (AI-suggested keywords based on competitor gaps) ---

class KeywordOpportunity(BaseModel):
    keyword: str
    reason: str


# --- opportunities ---

class OpportunitySeverity(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Opportunity(BaseModel):
    type: OpportunityType
    severity: OpportunitySeverity
    page_id: int
    page_url: str
    title: str
    detail: str
    suggested_fix: Optional[str] = None
    check_type: Optional[str] = None  # set for audit_* types - lets the frontend link into CheckList's suggestion action
    keyword: Optional[str] = None  # set for keyword_* types
    applied: bool = False  # a pending AppliedFix exists - user says they applied this, awaiting the next scan/check


# --- applied fixes (track/verify loop - Signal roadmap Phase D) ---

class ApplyFixRequest(BaseModel):
    type: OpportunityType
    check_type: Optional[str] = None
    keyword: Optional[str] = None


class AppliedFixRead(BaseModel):
    id: int
    page_id: int
    type: OpportunityType
    check_type: Optional[str]
    keyword: Optional[str]
    applied_at: datetime
    resolved: bool
    resolved_at: Optional[datetime]


# --- ranking action plan (AI guidance for a keyword with no/low rank) ---

class RankingActionPlan(BaseModel):
    plan: str


# --- site health rollup (Signal roadmap Phase E) ---

class ScoreTrendPoint(BaseModel):
    date: datetime
    score: float  # average of each page's latest-as-of-then score - see app/services/site_health.py


class ScoreMovement(BaseModel):
    page_id: int
    page_url: str
    previous_score: int
    new_score: int
    delta: int  # new - previous; positive means it improved


class KeywordMovement(BaseModel):
    page_id: int
    page_url: str
    keyword: str
    previous_rank: Optional[int]  # None = wasn't found in the previous check
    new_rank: Optional[int]  # None = not found in the latest check
    delta: int  # previous - new (positive = improved); a found/lost transition uses a large sentinel for sorting


class SiteHealth(BaseModel):
    score_trend: List[ScoreTrendPoint]
    score_wins: List[ScoreMovement]
    score_losses: List[ScoreMovement]
    keyword_wins: List[KeywordMovement]
    keyword_losses: List[KeywordMovement]
    top_opportunities: List[Opportunity]


# --- Google integration (Search Console + Analytics) ---

class GoogleAuthorizeResponse(BaseModel):
    authorize_url: str


class GAPropertyOption(BaseModel):
    property_id: str
    display_name: str


class GoogleConnectionStatus(BaseModel):
    connected: bool
    connected_at: Optional[datetime] = None
    gsc_properties: List[str] = []
    ga_properties: List[GAPropertyOption] = []


class GSCQueryRow(BaseModel):
    query: str
    clicks: int
    impressions: int
    ctr: float  # percent
    position: float


class GSCIndexStatus(BaseModel):
    indexed: bool
    verdict: str
    coverage_state: str
    last_crawl_time: Optional[str] = None


class GAPageMetrics(BaseModel):
    sessions: int
    pageviews: int
    bounce_rate: float  # percent
    avg_session_duration: float  # seconds


# --- alerts ---

class AlertRead(BaseModel):
    id: int
    page_id: int
    site_id: int  # not on the Alert row itself - joined from Page so the frontend can link straight to the page
    alert_type: AlertType
    message: str
    read: bool
    created_at: datetime


# --- pricing (public) / billing (signed-in user) ---

class PlanLimitsRead(BaseModel):
    max_sites: Optional[int] = None  # None = unlimited
    max_pages_per_site: Optional[int] = None
    max_keywords_per_page: Optional[int] = None


class PricingPlan(BaseModel):
    key: str  # "free" | "pro" | "agency"
    name: str
    price_cents: int
    interval: Optional[str] = None
    description: Optional[str] = None
    limits: PlanLimitsRead
    product_key: Optional[str] = None  # what to pass to POST /billing/checkout
    purchasable: bool = False  # billing configured AND a Dodo product linked


class PricingCreditPack(BaseModel):
    key: str
    name: str
    price_cents: int
    credits: int
    description: Optional[str] = None
    purchasable: bool = False


class PricingResponse(BaseModel):
    billing_enabled: bool
    plans: List[PricingPlan]
    credit_packs: List[PricingCreditPack]


class CheckoutRequest(BaseModel):
    product_key: str


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalResponse(BaseModel):
    url: str


class BillingPaymentRead(BaseModel):
    id: int
    amount_cents: int
    kind: str
    plan: Optional[str] = None
    credits_granted: int
    paid_at: datetime


class BillingSummary(BaseModel):
    plan: PlanTier
    credits_balance: int
    billing_enabled: bool
    has_subscription: bool
    can_manage_billing: bool
    payments: List[BillingPaymentRead]


# --- admin ---

class AdminUserRow(BaseModel):
    id: int
    email: str
    plan: PlanTier
    credits_balance: int
    created_at: datetime
    sites_count: int
    total_paid_cents: int
    last_active_at: Optional[datetime] = None
    is_admin: bool = False


class AdminUserList(BaseModel):
    items: List[AdminUserRow]
    total: int
    page: int
    page_size: int


class AdminSiteRow(BaseModel):
    id: int
    domain: str
    verified: bool
    pages_count: int


class AdminPaymentRow(BaseModel):
    id: int
    amount_cents: int
    tax_cents: int
    kind: str
    plan: Optional[str] = None
    credits_granted: int
    provider: str
    provider_ref: Optional[str] = None
    note: Optional[str] = None
    paid_at: datetime


class AdminLedgerRow(BaseModel):
    id: int
    delta: int
    balance_after: int
    reason: str
    ref: Optional[str] = None
    note: Optional[str] = None
    actor_email: Optional[str] = None
    created_at: datetime


class AdminAuditRow(BaseModel):
    id: int
    action: str
    actor_email: Optional[str] = None
    target_user_id: Optional[int] = None
    payload: Optional[str] = None
    created_at: datetime


class AdminUserDetail(BaseModel):
    id: int
    email: str
    plan: PlanTier
    credits_balance: int
    created_at: datetime
    is_admin: bool
    google_connected: bool
    dodo_customer_id: Optional[str] = None
    dodo_subscription_id: Optional[str] = None
    total_paid_cents: int
    last_active_at: Optional[datetime] = None
    sites: List[AdminSiteRow]
    payments: List[AdminPaymentRow]
    ledger: List[AdminLedgerRow]
    audit: List[AdminAuditRow]


class AdminStats(BaseModel):
    total_users: int
    signups_7d: int
    signups_30d: int
    users_by_plan: dict
    paying_users: int
    revenue_all_cents: int
    revenue_30d_cents: int
    estimated_mrr_cents: int
    credits_outstanding: int
    credits_spent_30d: int
    recent_signups: List[AdminUserRow]
    recent_actions: List[AdminAuditRow]


class CreditAdjustRequest(BaseModel):
    delta: int
    note: str = Field(min_length=3, max_length=500)

    @field_validator("delta")
    @classmethod
    def validate_delta(cls, v: int) -> int:
        if v == 0:
            raise ValueError("delta must not be zero")
        if abs(v) > 10_000:
            raise ValueError("delta must be between -10000 and 10000")
        return v


class PlanChangeRequest(BaseModel):
    plan: PlanTier
    note: str = Field(min_length=3, max_length=500)


class ManualPaymentRequest(BaseModel):
    amount_cents: int = Field(ge=0, le=10_000_000)
    credits: int = Field(default=0, ge=0, le=100_000)
    plan: Optional[PlanTier] = None  # also switch the user to this plan
    note: str = Field(min_length=3, max_length=500)
    paid_at: Optional[datetime] = None


class ProductRead(BaseModel):
    id: int
    key: str
    name: str
    kind: str
    price_cents: int
    interval: Optional[str] = None
    plan: Optional[str] = None
    credits: int
    dodo_product_id: Optional[str] = None
    description: Optional[str] = None
    active: bool
    sort_order: int
    updated_at: datetime


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    price_cents: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    credits: Optional[int] = Field(default=None, ge=0, le=100_000)
    dodo_product_id: Optional[str] = Field(default=None, max_length=120)  # "" clears the link
    description: Optional[str] = Field(default=None, max_length=300)
    active: Optional[bool] = None
    sort_order: Optional[int] = None


class ProductCreate(BaseModel):
    """Only credit packs can be created - the subscription tiers (Pro, Agency)
    are fixed by PLAN_LIMITS and are seeded by the migration."""
    key: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    name: str = Field(min_length=1, max_length=80)
    price_cents: int = Field(ge=0, le=10_000_000)
    credits: int = Field(gt=0, le=100_000)
    dodo_product_id: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=300)


class ProductVerifyResult(BaseModel):
    ok: bool
    message: str
    dodo_price_cents: Optional[int] = None
    dodo_currency: Optional[str] = None
