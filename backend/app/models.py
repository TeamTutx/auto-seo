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
# Real money: every one of these is a SerpApi or OpenAI call, so this is a
# growth lever with a direct cost - expect it to be tuned.
#
# Read through this module (models.SIGNUP_CREDITS), never copied into another
# module's namespace at import time, so changing it changes every reader at
# once and tests can pin it. See User.credits_balance below.
SIGNUP_CREDITS = 10


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str
    plan: PlanTier = Field(default=PlanTier.free)
    # default_factory, not default: a plain default is captured when the class
    # is defined, which would freeze SIGNUP_CREDITS at import time and make the
    # value impossible to change for a running process or a test.
    credits_balance: int = Field(default_factory=lambda: SIGNUP_CREDITS)
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
    # How this page got here: "manual" (typed in), "sitemap" or "link" (found by
    # the crawler - app/services/crawler.py).
    discovered_via: str = Field(default="manual")
    # Whether Google has this page in its index. "indexed" / "not_indexed" /
    # None = never checked. `index_source` is "gsc" (free, authoritative, needs
    # the user's Search Console) or "serp" (a paid site: lookup fallback).
    index_status: Optional[str] = Field(default=None)
    index_detail: Optional[str] = Field(default=None)  # Google's coverage wording
    index_source: Optional[str] = Field(default=None)
    index_checked_at: Optional[datetime] = Field(default=None)

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


# --- crawling, keyword discovery, visibility (Phase J in plan.md) ---
#
# These three all run as background jobs: crawling a site, asking Google and an
# LLM about a list of keywords, and reading Search Console take minutes, not the
# milliseconds a request should last. SiteJob is what the UI polls.


class JobKind(str, Enum):
    crawl = "crawl"
    keywords = "keywords"
    visibility = "visibility"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class SiteJob(SQLModel, table=True):
    """One background run. `progress`/`total` drive the progress bar; `message`
    is the human sentence under it. Stored as plain strings, not DB enums, for
    the reason in the block comment above Product."""
    id: Optional[int] = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id", index=True)
    kind: str
    status: str = Field(default=JobStatus.queued.value)
    progress: int = 0
    total: int = 0
    message: Optional[str] = None
    error: Optional[str] = None
    credits_spent: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class KeywordIdea(SQLModel, table=True):
    """A keyword Signal suggests the site could target, and where the idea came
    from. `source` is "gsc" (queries the site already gets impressions for -
    real data), "ai" (read off the page's own content) or "serp" (Google's
    related searches). Only gsc ideas carry impression/click/position numbers;
    Signal has no search-volume database, so the rest are ideas, not estimates.
    """
    __table_args__ = (UniqueConstraint("site_id", "keyword", name="uq_keywordidea_site_keyword"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id", index=True)
    keyword: str
    source: str
    rationale: Optional[str] = None  # why the AI thinks it fits
    impressions: Optional[int] = None
    clicks: Optional[int] = None
    position: Optional[float] = None
    # Set when the owner says "yes, I want to rank for this" - targeted ideas
    # are what a visibility run checks.
    targeted: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class VisibilityCheck(SQLModel, table=True):
    """Whether a site showed up for a keyword, per engine, at a point in time.

    `engine` is "google" (classic organic results), "google_ai_overview" (the AI
    answer box above them) or "chatgpt". `present` means ranked, cited, or
    mentioned respectively - deliberately one column, because the question the
    owner is asking is the same for all three: "did we show up?"
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id", index=True)
    keyword: str
    engine: str
    present: bool = False
    position: Optional[int] = None  # organic rank, google engine only
    detail: Optional[str] = None  # citing URL, or the sentence that mentioned us
    # JSON: who *did* win this search. Top organic results for the google engine,
    # cited sources for the AI Overview. Captured here because the check already
    # fetched them - asking again later would cost another credit and, worse,
    # would be advice about a different search than the one displayed.
    context: Optional[str] = None
    checked_at: datetime = Field(default_factory=datetime.utcnow)


class GeneratedResult(SQLModel, table=True):
    """The output of something the user paid a credit for, kept so a refresh
    doesn't throw it away.

    Without this, every AI suggestion and competitor lookup lived in React state
    only: you spent a credit, reloaded the page, and had to spend another to see
    the same answer. One row per (page, kind, subject) - the newest replaces the
    last, because these are "what should I do now" answers, not a history.
    `subject` is the keyword for keyword-scoped results and "" for page-scoped
    ones; an empty string rather than NULL because Postgres treats NULLs as
    distinct in a unique constraint, which would let duplicates through."""
    __table_args__ = (
        UniqueConstraint("page_id", "kind", "subject", name="uq_generatedresult_page_kind_subject"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="page.id", index=True)
    kind: str  # "meta_description", "competitors", "action_plan", …
    subject: str = ""
    payload: str  # JSON, shaped by kind
    created_at: datetime = Field(default_factory=datetime.utcnow)


class VisibilityAdvice(SQLModel, table=True):
    """What to actually do to become visible for one keyword.

    Stored rather than regenerated so re-reading costs nothing, and stamped with
    the reading it was derived from - advice about a search that has since moved
    is worse than no advice, and the UI says so when the two drift apart."""
    id: Optional[int] = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id", index=True)
    keyword: str
    diagnosis: str
    actions: str  # JSON list of {title, detail, addresses}
    target_page_url: Optional[str] = None
    based_on_checked_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# --- applying fixes (Phase K in plan.md) ---
#
# Signal reads a suggestion it already generates, compiles it into an exact
# before/after, and - where the site is connected to somewhere writable - sets
# it. Two rules shape both tables below.
#
# **Only head-level and attribute-level fields.** Every field in APPLICABLE_FIELDS
# is a meta tag, a link tag, a title, a JSON-LD block or an image attribute.
# Nothing here edits prose: rewriting someone's paragraphs has a different
# failure mode from setting a tag - not a wrong tag, but a page that no longer
# says what the business meant - so content suggestions stay drafts.
#
# **Nothing is written without a way back.** `before` is captured from the live
# page at compile time, so revert is an exact restore, and a change whose live
# value no longer matches `before` is refused rather than applied over whoever
# edited the page in between.


class WriteTargetKind(str, Enum):
    """Where a site's content lives. Plain-string column, as with SiteJob.kind -
    see the block comment above Product for why these are not Postgres enums."""
    wordpress = "wordpress"
    github = "github"


class ChangeStatus(str, Enum):
    proposed = "proposed"
    applied = "applied"
    reverted = "reverted"
    failed = "failed"


# What Signal can actually set, mapped to the audit check that asks for it.
# A field absent from here is advice, and the UI must not offer to apply it.
APPLICABLE_FIELDS = (
    "title_tag",
    "meta_description",
    "canonical_tag",
    "robots_meta_tag",
    "structured_data",
    "image_alt_text",
)


class SiteWriteTarget(SQLModel, table=True):
    """Where to write this site's changes. One per site: a site's content lives
    in one place, and letting two targets claim the same site would mean writing
    a change twice or silently picking one.

    **No row means manual** - the change is shown as an exact before/after to
    copy. That is the default for every site and it is not a degraded mode; it
    is what an unconnected site gets, and it works for all of them.

    The credential is encrypted with the same key as a Google refresh token
    (app/services/token_crypto.py) and for the same reason: a WordPress
    application password or a GitHub token is standing write access to the
    user's site, which is strictly worse than a leaked session."""
    id: Optional[int] = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id", index=True, unique=True)
    kind: str
    # JSON. WordPress: {base_url, username, capabilities: [...]}. GitHub:
    # {repo, branch}. `capabilities` is what a connect-time probe found the
    # target can actually write - a WordPress without an SEO plugin exposing
    # its REST fields cannot set a meta description, and promising otherwise
    # would be a button that fails.
    config: str = Field(default="{}")
    secret_encrypted: str
    status: str = Field(default="untested")  # "ok" | "failed" | "untested"
    status_detail: Optional[str] = Field(default=None)
    last_checked_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ProposedChange(SQLModel, table=True):
    """One exact edit: this field on this page goes from `before` to `after`.

    This is also the durable record of what a credit bought, deliberately not a
    GeneratedResult row. That table's contract is "newest replaces, no history",
    which is right for "what should I do now" answers and wrong here: applying
    and reverting *are* history, and overwriting them would lose the record of a
    change made to someone's live site."""
    id: Optional[int] = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id", index=True)
    # Null for a change that is not about an existing tracked page (a new page
    # the advice says to publish). Those are drafts, never applied.
    page_id: Optional[int] = Field(default=None, foreign_key="page.id", index=True)
    field: str  # one of APPLICABLE_FIELDS
    # Distinguishes several changes to the same field on one page: the image src
    # for alt text, "" for everything else. Empty string rather than NULL, as
    # with GeneratedResult.subject.
    subject: str = Field(default="")
    origin: str  # "audit_check" | "visibility_advice" | "keyword_action_plan"
    origin_ref: Optional[str] = Field(default=None)  # the check_type, or the keyword
    before: Optional[str] = Field(default=None)  # None = the field is absent from the page
    after: str
    status: str = Field(default=ChangeStatus.proposed.value)
    target_kind: Optional[str] = Field(default=None)  # which channel applied it
    receipt: Optional[str] = Field(default=None)  # JSON: the WordPress post id, or the PR url
    error: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    applied_at: Optional[datetime] = Field(default=None)
    reverted_at: Optional[datetime] = Field(default=None)


class AdminAuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    actor_id: Optional[int] = Field(default=None, foreign_key="user.id")  # None = system (webhook)
    action: str
    target_user_id: Optional[int] = Field(default=None, index=True)
    payload: Optional[str] = None  # JSON text
    created_at: datetime = Field(default_factory=datetime.utcnow)
