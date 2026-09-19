from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


class PlanTier(str, Enum):
    """Legacy. Signal is credit-based now: there is one tier and nothing to
    upgrade to, so every account is `free` and the limits below apply to all of
    them. The column is kept because `payment.plan` records what historical
    money bought, and because dropping a value from a Postgres enum is exactly
    the kind of change that broke production once (see CLAUDE.md)."""
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


class AlertType(str, Enum):
    score_drop = "score_drop"
    new_fail = "new_fail"
    fix_verified = "fix_verified"


class OpportunityType(str, Enum):
    audit_fail = "audit_fail"
    audit_warning = "audit_warning"
    keyword_not_found = "keyword_not_found"
    keyword_low_rank = "keyword_low_rank"
    keyword_rank_drop = "keyword_rank_drop"


# The same limits for every account. Signal charges for credits, not for tiers:
# everything that costs Signal real money (rank lookups, AI suggestions) is
# metered in credits already, so these exist only to keep one scripted account
# from filling the database for free. Raising them costs nothing but storage.
ACCOUNT_LIMITS = {"max_sites": 5, "max_pages_per_site": 50, "max_keywords_per_page": 25}

# What a new account starts with, so it can try Signal before buying credits.
# Real money: every one of these is a SerpApi or OpenAI call.
SIGNUP_CREDITS = 3


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str
    plan: PlanTier = Field(default=PlanTier.free)
    credits_balance: int = Field(default=SIGNUP_CREDITS)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Set from Dodo webhooks (app/services/dodo_webhooks.py): the customer id
    # lets us open the billing portal, the subscription id ties renewals and
    # cancellations back to this user.
    dodo_customer_id: Optional[str] = Field(default=None, index=True)
    dodo_subscription_id: Optional[str] = Field(default=None, index=True)

    sites: List["Site"] = Relationship(back_populates="user")


class Site(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    domain: str
    verified: bool = Field(default=False)
    verification_method: Optional[VerificationMethod] = Field(default=None)
    verification_token: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Which Search Console / Analytics property (from the user's connected
    # Google account - see GoogleConnection) this site's real traffic/search
    # data comes from. Picked by the user in Settings, since one Google
    # account can have access to several properties and there's no reliable
    # way to guess which one maps to this site's domain.
    gsc_property: Optional[str] = Field(default=None)  # e.g. "sc-domain:example.com" or "https://example.com/"
    ga_property_id: Optional[str] = Field(default=None)  # GA4 numeric property id

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
    location_code: int = Field(default=2356)  # DataForSEO/SerpApi location code, 2356 = India
    language_code: str = Field(default="en")
    device: str = Field(default="desktop")
    checked_at: datetime = Field(default_factory=datetime.utcnow)

    page: Optional[Page] = Relationship(back_populates="keyword_ranks")


class Alert(SQLModel, table=True):
    """In-app notifications for scheduled audits (REQUIREMENTS.md §2.7, §3.1
    "Scheduled automated audits + alerts" - paid-tier only). Email delivery
    needs a Resend/SendGrid key we don't have yet, so this is the in-app
    substitute for now - see app/workers/tasks.py."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    page_id: int = Field(foreign_key="page.id", index=True)
    alert_type: AlertType
    message: str
    read: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AppliedFix(SQLModel, table=True):
    """Track/verify loop for AI-suggested fixes (Signal roadmap Phase D -
    plan.md). Signal has no write access to a user's actual site, so a user
    applies a suggestion themselves and tells us via POST .../opportunities/apply;
    the baseline captured here lets the next audit/rank check (which already
    happens on every rescan/recheck, not just Pro/Agency's scheduled ones)
    confirm whether the underlying issue actually cleared."""
    id: Optional[int] = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="page.id", index=True)
    opportunity_type: OpportunityType
    check_type: Optional[str] = Field(default=None)  # set for audit_fail / audit_warning
    keyword: Optional[str] = Field(default=None)  # set for the keyword_* types
    baseline_score: Optional[int] = Field(default=None)  # audit score when marked applied
    baseline_rank: Optional[int] = Field(default=None)  # rank_position when marked applied (None = not found)
    applied_at: datetime = Field(default_factory=datetime.utcnow)
    resolved: bool = Field(default=False)
    resolved_at: Optional[datetime] = Field(default=None)


class GoogleConnection(SQLModel, table=True):
    """One connected Google account per Signal user (Search Console +
    Analytics are just scopes on the same OAuth grant - see
    app/services/google_oauth.py). Tokens are encrypted at rest
    (app/services/token_crypto.py) since a leaked refresh token grants
    standing access to the user's real Google data, unlike a session
    cookie."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, unique=True)
    access_token_encrypted: str
    refresh_token_encrypted: str
    token_expires_at: datetime
    scope: str = Field(default="")
    connected_at: datetime = Field(default_factory=datetime.utcnow)


# --- Billing / admin (Phase H in plan.md) ---
#
# Deliberately plain string columns instead of Postgres enums for kind/reason/
# provider: SQLite (tests, dev) doesn't enforce enum labels but Postgres does,
# which once broke every audit in production (see CLAUDE.md), and a new value
# must never need an `ALTER TYPE`. Validation lives in the API schemas.


class CreditReason(str, Enum):
    opening_balance = "opening_balance"  # ledger backfill for pre-existing users
    signup = "signup"
    usage = "usage"
    admin = "admin"
    purchase = "purchase"
    refund = "refund"


class PaymentKind(str, Enum):
    credit_pack = "credit_pack"
    subscription = "subscription"
    manual = "manual"
    refund = "refund"


class Product(SQLModel, table=True):
    """A credit pack: what's for sale, and what the public pricing section
    shows. Created and edited from the admin panel (/admin/pricing) - the owner
    can have as many as they like, and the landing page renders whatever is
    active, in sort_order. The displayed price is informational; the amount
    actually charged is whatever the linked Dodo product says, so the admin page
    can compare the two (POST /admin/products/{id}/verify).

    `kind`/`interval`/`plan` are leftovers from the subscription catalog that
    migration 0009 removed. They stay so old `payment` rows still make sense and
    so a subscription product could be reintroduced without a schema change."""
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)  # "credits_10" - stable, used by checkout
    name: str
    kind: str = "credit_pack"  # "credit_pack" | "subscription" (unused)
    price_cents: int
    interval: Optional[str] = None  # "month" for subscriptions
    plan: Optional[str] = None  # PlanTier value a subscription grants
    credits: int = 0  # credits this pack grants
    dodo_product_id: Optional[str] = None
    description: Optional[str] = None
    badge: Optional[str] = None  # e.g. "Best value" - shown on the pricing card
    active: bool = True
    sort_order: int = 0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CreditTransaction(SQLModel, table=True):
    """Every change to User.credits_balance, written in the same transaction as
    the change itself (app/services/credits.py) - so the ledger always sums to
    the balance."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    delta: int
    balance_after: int
    reason: str
    ref: Optional[str] = None  # what was spent on, e.g. "keyword_check"
    note: Optional[str] = None
    actor_id: Optional[int] = Field(default=None, foreign_key="user.id")  # the admin, if any
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Payment(SQLModel, table=True):
    """Money received (or returned: refunds are negative rows). amount_cents is
    what the customer paid *excluding tax*, in USD; tax_cents is recorded
    separately so partial refunds can be prorated. Dodo's own fee is not
    deducted - this is gross revenue."""
    __table_args__ = (UniqueConstraint("provider", "provider_ref", name="uq_payment_provider_ref"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    amount_cents: int
    tax_cents: int = 0
    kind: str
    plan: Optional[str] = None
    product_key: Optional[str] = None  # the Product this bought, when there was one
    credits_granted: int = 0
    provider: str  # "manual" | "dodo"
    provider_ref: Optional[str] = None  # Dodo payment/refund id - webhook idempotency
    note: Optional[str] = None
    actor_id: Optional[int] = Field(default=None, foreign_key="user.id")
    paid_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AdminAuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    actor_id: Optional[int] = Field(default=None, foreign_key="user.id")  # None = system (webhook)
    action: str
    target_user_id: Optional[int] = Field(default=None, index=True)
    payload: Optional[str] = None  # JSON text
    created_at: datetime = Field(default_factory=datetime.utcnow)
