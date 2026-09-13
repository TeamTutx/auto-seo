from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr

from app.models import CheckStatus, PlanTier, VerificationMethod


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


class SiteRead(BaseModel):
    id: int
    domain: str
    verified: bool
    verification_method: Optional[VerificationMethod]
    verification_token: str
    created_at: datetime


class SiteVerifyRequest(BaseModel):
    method: VerificationMethod


# --- pages ---

class PageCreate(BaseModel):
    url: str
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


class KeywordRankRead(BaseModel):
    id: int
    page_id: int
    keyword: str
    rank_position: Optional[int]
    provider: Optional[str]
    checked_at: datetime
