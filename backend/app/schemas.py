import re
from datetime import datetime
from enum import Enum
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, EmailStr, field_validator

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
