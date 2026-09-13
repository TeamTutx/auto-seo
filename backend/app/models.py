from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class PlanTier(str, Enum):
    free = "free"
    pro = "pro"
    agency = "agency"


class VerificationMethod(str, Enum):
    dns_txt = "dns_txt"
    meta_tag = "meta_tag"
    file_upload = "file_upload"


class CheckStatus(str, Enum):
    pass_ = "pass"
    warning = "warning"
    fail = "fail"


# Plan limits referenced by routers when enforcing free/paid gates (REQUIREMENTS.md §3.1)
PLAN_LIMITS = {
    PlanTier.free: {"max_sites": 1, "max_pages_per_site": 5, "max_keywords_per_page": 3},
    PlanTier.pro: {"max_sites": 5, "max_pages_per_site": 50, "max_keywords_per_page": 50},
    PlanTier.agency: {"max_sites": None, "max_pages_per_site": None, "max_keywords_per_page": None},
}


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str
    plan: PlanTier = Field(default=PlanTier.free)
    credits_balance: int = Field(default=3)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    sites: List["Site"] = Relationship(back_populates="user")


class Site(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    domain: str
    verified: bool = Field(default=False)
    verification_method: Optional[VerificationMethod] = Field(default=None)
    verification_token: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    user: Optional[User] = Relationship(back_populates="sites")
    pages: List["Page"] = Relationship(back_populates="site")


class Page(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id", index=True)
    url: str
    target_keyword: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    site: Optional[Site] = Relationship(back_populates="pages")
    audits: List["Audit"] = Relationship(back_populates="page")
    keyword_ranks: List["KeywordRank"] = Relationship(back_populates="page")


class Audit(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="page.id", index=True)
    score: Optional[int] = Field(default=None)
    extracted_title: Optional[str] = Field(default=None)
    word_count: Optional[int] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    page: Optional[Page] = Relationship(back_populates="audits")
    checks: List["Check"] = Relationship(back_populates="audit")


class Check(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    audit_id: int = Field(foreign_key="audit.id", index=True)
    check_type: str
    status: CheckStatus
    message: str
    suggested_fix: Optional[str] = Field(default=None)

    audit: Optional[Audit] = Relationship(back_populates="checks")


class KeywordRank(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="page.id", index=True)
    keyword: str
    rank_position: Optional[int] = Field(default=None)
    provider: Optional[str] = Field(default=None)
    # Rank varies by search location/language/device, so each measurement
    # records what it was checked against - without this, comparing two
    # rows over time is meaningless if the defaults ever change.
    location_code: int = Field(default=2840)  # DataForSEO location code, 2840 = United States
    language_code: str = Field(default="en")
    device: str = Field(default="desktop")
    checked_at: datetime = Field(default_factory=datetime.utcnow)

    page: Optional[Page] = Relationship(back_populates="keyword_ranks")
