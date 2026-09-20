import re
from datetime import datetime
from enum import Enum
from typing import List, Optional
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models import AlertType, CheckStatus, OpportunityType, VerificationMethod

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


def _clean_page_url(value: str) -> str:
    """Tidy a hand-typed page URL without changing which page it names.

    Search Console matches a page by exact URL, so a stored URL that differs
    from the real one by a scheme, a capital letter in the host or a stray
    fragment silently returns no search data at all - indistinguishable from a
    page that genuinely gets no traffic. The trailing slash is left exactly as
    typed: it is the site's choice of canonical form, not noise (see
    app/services/crawler.py), and the Search Console lookup tries both anyway.
    """
    value = (value or "").strip()
    if not value:
        raise ValueError("Enter a page URL")

    # Only add a scheme when there genuinely isn't one. Testing for "//" instead
    # would turn "javascript:alert(1)" into "https://javascript:alert(1)" - a
    # nonsense host that then passes every later check.
    scheme = re.match(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):", value)
    if scheme is None:
        value = f"https://{value}"
    elif scheme.group(1).lower() not in ("http", "https"):
        raise ValueError(f'"{value}" isn\'t a web page address (it must start with http:// or https://)')

    parsed = urlparse(value)
    if not parsed.hostname or not _DOMAIN_RE.match(parsed.hostname):
        raise ValueError(
            f'"{value}" doesn\'t look like a page URL (expected something like https://example.com/pricing)'
        )
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path or "/",
        parsed.params,
        parsed.query,
        "",  # a fragment is a position within a page, never a different page
    ))


# --- auth ---

class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    id: int
    email: EmailStr
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

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        return _clean_page_url(v)


class PageUpdate(BaseModel):
    url: Optional[str] = None
    target_keyword: Optional[str] = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        return _clean_page_url(v) if v is not None else v


class PageRead(BaseModel):
    id: int
    site_id: int
    url: str
    target_keyword: Optional[str]
    created_at: datetime
    discovered_via: str = "manual"
    index_status: Optional[str] = None  # "indexed" | "not_indexed" | "unknown" | None = unchecked
    index_detail: Optional[str] = None
    index_source: Optional[str] = None  # "gsc" (authoritative) | "serp" (inferred)
    index_checked_at: Optional[datetime] = None


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

class AccountLimitsRead(BaseModel):
    max_sites: Optional[int] = None  # None = unlimited
    max_pages_per_site: Optional[int] = None
    max_keywords_per_page: Optional[int] = None


class PricingCreditPack(BaseModel):
    key: str  # what to pass to POST /billing/checkout
    name: str
    price_cents: int
    credits: int
    description: Optional[str] = None
    badge: Optional[str] = None
    price_per_credit_cents: Optional[float] = None
    purchasable: bool = False  # billing configured AND a Dodo product linked


class PricingResponse(BaseModel):
    """Signal is credit-based: there are no tiers, so the same limits apply to
    every account and the only thing to buy is a pack of credits."""
    billing_enabled: bool
    signup_credits: int
    limits: AccountLimitsRead
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
    product_key: Optional[str] = None
    credits_granted: int
    paid_at: datetime


class BillingSummary(BaseModel):
    credits_balance: int
    credits_purchased: int  # lifetime, so the page can show more than a balance
    billing_enabled: bool
    can_manage_billing: bool
    packs: List[PricingCreditPack]
    payments: List[BillingPaymentRead]


# --- crawling, keyword discovery, visibility ---

class GeneratedResultRead(BaseModel):
    """Something a credit already paid for, read back so a refresh doesn't lose
    it. `payload`'s shape depends on `kind` - the UI casts it."""
    kind: str
    subject: str = ""  # the keyword, for keyword-scoped results
    payload: object
    created_at: datetime


class KeywordAddRequest(BaseModel):
    keyword: str = Field(min_length=2, max_length=200)


class SiteJobRead(BaseModel):
    """What the UI polls while a background run is in flight."""
    id: int
    kind: str
    status: str  # queued | running | done | failed
    progress: int
    total: int
    message: Optional[str] = None
    error: Optional[str] = None
    credits_spent: int
    created_at: datetime
    finished_at: Optional[datetime] = None


class SiteJobs(BaseModel):
    """The latest run of each kind, so the UI polls one endpoint, not three."""
    crawl: Optional[SiteJobRead] = None
    keywords: Optional[SiteJobRead] = None
    visibility: Optional[SiteJobRead] = None


class KeywordIdeaRead(BaseModel):
    id: int
    keyword: str
    source: str  # "gsc" (measured) | "ai" | "serp"
    rationale: Optional[str] = None
    impressions: Optional[int] = None
    clicks: Optional[int] = None
    position: Optional[float] = None
    targeted: bool


class KeywordTargetRequest(BaseModel):
    """Which ideas the owner actually wants to rank for."""
    ids: List[int] = Field(min_length=1, max_length=200)
    targeted: bool = True


class VisibilityEngineRead(BaseModel):
    engine: str  # "google" | "google_ai_overview" | "chatgpt"
    present: bool
    position: Optional[int] = None
    detail: Optional[str] = None
    checked_at: datetime


class VisibilityActionRead(BaseModel):
    title: str
    detail: str = ""
    addresses: str = "both"  # "google" | "ai" | "both" - they're different problems


class VisibilityAdviceRead(BaseModel):
    diagnosis: str
    actions: List[VisibilityActionRead]
    target_page_url: Optional[str] = None
    created_at: datetime
    # True when the keyword has been re-checked since this was written, so the
    # UI can say the advice describes a search that has moved on.
    stale: bool = False


class VisibilityKeywordRead(BaseModel):
    keyword: str
    engines: List[VisibilityEngineRead]
    advice: Optional[VisibilityAdviceRead] = None


class VisibilityAdviceRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=200)


class VisibilityCheckRequest(BaseModel):
    """Which keywords a visibility run covers. Omitted (or a null keyword) means
    all of them; a keyword means just that one, so re-checking whether one
    ranking moved costs 2 credits rather than 2 per keyword on the site."""
    keyword: Optional[str] = Field(default=None, max_length=200)


class VisibilityReport(BaseModel):
    """One row per targeted keyword, newest reading per engine."""
    checked_at: Optional[datetime] = None
    targeted_keywords: int
    google_visible: int
    ai_overview_cited: int
    chatgpt_mentions: int
    keywords: List[VisibilityKeywordRead]


class TrendPoint(BaseModel):
    date: str  # YYYY-MM-DD
    clicks: int
    impressions: int
    position: Optional[float] = None


class SearchPresence(BaseModel):
    """What the site page leads with: one gauge for Google, one for AI answers,
    and the home page's search trend behind them. Derived entirely from data
    already stored, so opening the page costs nothing."""
    # Google + AI gauges
    targeted_keywords: int
    checked_keywords: int  # how many of those have actually been checked
    google_visible: int
    google_score: Optional[int] = None  # percent, None = nothing checked yet
    best_position: Optional[int] = None
    ai_visible: int
    ai_score: Optional[int] = None
    ai_overview_cited: int
    chatgpt_mentions: int
    last_checked_at: Optional[datetime] = None

    # Trend for the home page
    trend_page_url: Optional[str] = None
    trend: List[TrendPoint] = []
    clicks_total: int = 0
    impressions_total: int = 0
    clicks_change: Optional[int] = None  # percent vs the previous week
    impressions_change: Optional[int] = None
    average_position: Optional[float] = None
    # Why there's no trend line, when there isn't one: "no_google", "no_property",
    # "no_pages", "no_data", or None when there is.
    trend_unavailable: Optional[str] = None


class IndexSummary(BaseModel):
    total_pages: int
    indexed: int
    not_indexed: int
    unchecked: int
    source: Optional[str] = None  # what answered most recently


# --- admin ---

class AdminUserRow(BaseModel):
    id: int
    email: str
    credits_balance: int
    credits_purchased: int
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
    product_key: Optional[str] = None
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
    credits_balance: int
    credits_purchased: int
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
    paying_users: int
    revenue_all_cents: int
    revenue_30d_cents: int
    credits_sold_all: int
    credits_sold_30d: int
    credits_outstanding: int  # bought or granted but not yet spent - a liability
    credits_spent_30d: int
    top_packs: List["AdminPackSales"]
    recent_signups: List[AdminUserRow]
    recent_actions: List[AdminAuditRow]


class AdminPackSales(BaseModel):
    """Revenue per credit pack, so the owner can see which price point sells."""
    product_key: str
    name: str
    sales: int
    revenue_cents: int
    credits_granted: int


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


class ManualPaymentRequest(BaseModel):
    """Money that arrived outside Dodo (UPI, bank transfer, an invoice)."""
    amount_cents: int = Field(ge=0, le=10_000_000)
    credits: int = Field(default=0, ge=0, le=100_000)
    note: str = Field(min_length=3, max_length=500)
    paid_at: Optional[datetime] = None


class ProductRead(BaseModel):
    id: int
    key: str
    name: str
    kind: str
    price_cents: int
    credits: int
    dodo_product_id: Optional[str] = None
    description: Optional[str] = None
    badge: Optional[str] = None
    active: bool
    sort_order: int
    sales: int = 0  # how many have been bought - a pack with sales can't be deleted
    updated_at: datetime


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    price_cents: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    credits: Optional[int] = Field(default=None, gt=0, le=100_000)
    dodo_product_id: Optional[str] = Field(default=None, max_length=120)  # "" clears the link
    description: Optional[str] = Field(default=None, max_length=300)
    badge: Optional[str] = Field(default=None, max_length=24)
    active: Optional[bool] = None
    sort_order: Optional[int] = None


class ProductCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    name: str = Field(min_length=1, max_length=80)
    price_cents: int = Field(ge=0, le=10_000_000)
    credits: int = Field(gt=0, le=100_000)
    dodo_product_id: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=300)
    badge: Optional[str] = Field(default=None, max_length=24)


class ProductReorderRequest(BaseModel):
    """Every pack id, in the order they should appear on the pricing page."""
    ids: List[int] = Field(min_length=1, max_length=50)


class ProductVerifyResult(BaseModel):
    ok: bool
    message: str
    dodo_price_cents: Optional[int] = None
    dodo_currency: Optional[str] = None
