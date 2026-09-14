import re
from datetime import datetime
from enum import Enum
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, EmailStr, field_validator

from app.models import AlertType, CheckStatus, PlanTier, VerificationMethod

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


# --- opportunities ---

class OpportunityType(str, Enum):
    audit_fail = "audit_fail"
    audit_warning = "audit_warning"
    keyword_not_found = "keyword_not_found"
    keyword_low_rank = "keyword_low_rank"
    keyword_rank_drop = "keyword_rank_drop"


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


# --- alerts ---

class AlertRead(BaseModel):
    id: int
    page_id: int
    site_id: int  # not on the Alert row itself - joined from Page so the frontend can link straight to the page
    alert_type: AlertType
    message: str
    read: bool
    created_at: datetime
