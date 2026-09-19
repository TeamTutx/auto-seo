"""Owner-only admin API: who the users are, what they've paid, and the levers to
change it (credits, plan, manual payments, the pricing catalog).

Every route depends on require_admin. Responses use explicit schemas built
field by field - never a raw User - so a password hash or OAuth token can't leak
by adding a column later. Every write is recorded in AdminAuditLog.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, func, select

from app.config import settings
from app.database import get_session
from app.deps import is_admin_user, require_admin
from app.models import (
    AdminAuditLog,
    Audit,
    CreditReason,
    CreditTransaction,
    GoogleConnection,
    Page,
    Payment,
    PaymentKind,
    PlanTier,
    Product,
    Site,
    User,
)
from app.schemas import (
    AdminAuditRow,
    AdminLedgerRow,
    AdminPaymentRow,
    AdminSiteRow,
    AdminStats,
    AdminUserDetail,
    AdminUserList,
    AdminUserRow,
    CreditAdjustRequest,
    ManualPaymentRequest,
    PlanChangeRequest,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    ProductVerifyResult,
)
from app.services import dodo
from app.services.billing import log_admin_action, record_payment, set_user_plan
from app.services.credits import InsufficientCredits, apply_credit_delta

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# Correlated scalar subqueries: one row per user with its aggregates, so the
# list can sort and filter on them in SQL (and stay correct when paginated).
_total_paid = (
    select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(Payment.user_id == User.id).correlate(User).scalar_subquery()
)
_sites_count = select(func.count(Site.id)).where(Site.user_id == User.id).correlate(User).scalar_subquery()
_last_scan = (
    select(func.max(Audit.created_at))
    .select_from(Audit)
    .join(Page, Page.id == Audit.page_id)
    .join(Site, Site.id == Page.site_id)
    .where(Site.user_id == User.id)
    .correlate(User)
    .scalar_subquery()
)

_SORTS = {
    "created_at": User.created_at,
    "email": User.email,
    "credits": User.credits_balance,
    "total_paid": _total_paid,
    "sites": _sites_count,
    "last_scan": _last_scan,
}


def _row(user: User, total_paid: int, sites_count: int, last_scan: Optional[datetime]) -> AdminUserRow:
    return AdminUserRow(
        id=user.id,
        email=user.email,
        plan=user.plan,
        credits_balance=user.credits_balance,
        created_at=user.created_at,
        sites_count=sites_count or 0,
        total_paid_cents=int(total_paid or 0),
        last_active_at=last_scan,
        is_admin=is_admin_user(user),
    )


def _get_user_or_404(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _emails(session: Session, ids: set) -> Dict[int, str]:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {u.id: u.email for u in session.exec(select(User).where(User.id.in_(ids))).all()}


def _audit_rows(session: Session, logs: List[AdminAuditLog]) -> List[AdminAuditRow]:
    emails = _emails(session, {log.actor_id for log in logs})
    return [
        AdminAuditRow(
            id=log.id,
            action=log.action,
            actor_email=emails.get(log.actor_id) if log.actor_id else None,
            target_user_id=log.target_user_id,
            payload=log.payload,
            created_at=log.created_at,
        )
        for log in logs
    ]


def _detail(session: Session, user: User) -> AdminUserDetail:
    total_paid, last_scan = session.exec(select(_total_paid, _last_scan).where(User.id == user.id)).one()

    site_rows = []
    for site in session.exec(select(Site).where(Site.user_id == user.id).order_by(Site.id)).all():
        pages = session.exec(select(func.count(Page.id)).where(Page.site_id == site.id)).one()
        site_rows.append(AdminSiteRow(id=site.id, domain=site.domain, verified=site.verified, pages_count=pages))

    payments = session.exec(
        select(Payment).where(Payment.user_id == user.id).order_by(Payment.paid_at.desc(), Payment.id.desc()).limit(100)
    ).all()
    ledger = session.exec(
        select(CreditTransaction).where(CreditTransaction.user_id == user.id).order_by(CreditTransaction.id.desc()).limit(100)
    ).all()
    logs = session.exec(
        select(AdminAuditLog).where(AdminAuditLog.target_user_id == user.id).order_by(AdminAuditLog.id.desc()).limit(50)
    ).all()
    actor_emails = _emails(session, {t.actor_id for t in ledger})

    return AdminUserDetail(
        id=user.id,
        email=user.email,
        plan=user.plan,
        credits_balance=user.credits_balance,
        created_at=user.created_at,
        is_admin=is_admin_user(user),
        google_connected=session.exec(select(GoogleConnection).where(GoogleConnection.user_id == user.id)).first() is not None,
        dodo_customer_id=user.dodo_customer_id,
        dodo_subscription_id=user.dodo_subscription_id,
        total_paid_cents=int(total_paid or 0),
        last_active_at=last_scan,
        sites=site_rows,
        payments=[
            AdminPaymentRow(
                id=p.id, amount_cents=p.amount_cents, tax_cents=p.tax_cents, kind=p.kind, plan=p.plan,
                credits_granted=p.credits_granted, provider=p.provider, provider_ref=p.provider_ref,
                note=p.note, paid_at=p.paid_at,
            )
            for p in payments
        ],
        ledger=[
            AdminLedgerRow(
                id=t.id, delta=t.delta, balance_after=t.balance_after, reason=t.reason, ref=t.ref, note=t.note,
                actor_email=actor_emails.get(t.actor_id) if t.actor_id else None, created_at=t.created_at,
            )
            for t in ledger
        ],
        audit=_audit_rows(session, logs),
    )


# --- overview ---

@router.get("/stats", response_model=AdminStats)
def stats(session: Session = Depends(get_session)):
    now = datetime.utcnow()
    d7, d30 = now - timedelta(days=7), now - timedelta(days=30)

    total_users = session.exec(select(func.count(User.id))).one()
    by_plan = {p.value: 0 for p in PlanTier}
    for plan, count in session.exec(select(User.plan, func.count(User.id)).group_by(User.plan)).all():
        by_plan[plan.value if isinstance(plan, PlanTier) else str(plan)] = count

    paying_users = len(
        session.exec(select(Payment.user_id).group_by(Payment.user_id).having(func.sum(Payment.amount_cents) > 0)).all()
    )
    revenue_all = session.exec(select(func.coalesce(func.sum(Payment.amount_cents), 0))).one()
    revenue_30d = session.exec(
        select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(Payment.paid_at >= d30)
    ).one()

    # Estimate: users currently on each paid plan x that plan's catalog price.
    mrr = 0
    for product in session.exec(select(Product).where(Product.kind == "subscription", Product.active == True)).all():  # noqa: E712
        mrr += by_plan.get(product.plan or "", 0) * product.price_cents

    spent = session.exec(
        select(func.coalesce(func.sum(CreditTransaction.delta), 0)).where(
            CreditTransaction.reason == CreditReason.usage.value, CreditTransaction.created_at >= d30
        )
    ).one()

    recent = session.exec(
        select(User, _total_paid, _sites_count, _last_scan).order_by(User.created_at.desc(), User.id.desc()).limit(5)
    ).all()
    logs = session.exec(select(AdminAuditLog).order_by(AdminAuditLog.id.desc()).limit(10)).all()

    return AdminStats(
        total_users=total_users,
        signups_7d=session.exec(select(func.count(User.id)).where(User.created_at >= d7)).one(),
        signups_30d=session.exec(select(func.count(User.id)).where(User.created_at >= d30)).one(),
        users_by_plan=by_plan,
        paying_users=paying_users,
        revenue_all_cents=int(revenue_all),
        revenue_30d_cents=int(revenue_30d),
        estimated_mrr_cents=int(mrr),
        credits_outstanding=int(session.exec(select(func.coalesce(func.sum(User.credits_balance), 0))).one()),
        credits_spent_30d=-int(spent),
        recent_signups=[_row(*r) for r in recent],
        recent_actions=_audit_rows(session, logs),
    )


# --- users ---

@router.get("/users", response_model=AdminUserList)
def list_users(
    q: Optional[str] = Query(default=None, max_length=100),
    plan: Optional[PlanTier] = None,
    paid: Optional[bool] = Query(default=None, description="true = has paid anything; false = never paid"),
    sort: str = Query(default="created_at"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_session),
):
    if sort not in _SORTS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"sort must be one of {sorted(_SORTS)}")

    conditions = []
    if q and q.strip():
        conditions.append(User.email.ilike(f"%{q.strip()}%"))
    if plan is not None:
        conditions.append(User.plan == plan)
    if paid is True:
        conditions.append(_total_paid > 0)
    elif paid is False:
        conditions.append(_total_paid <= 0)

    total = session.exec(select(func.count(User.id)).where(*conditions)).one()

    column = _SORTS[sort]
    ordering = column.asc() if order == "asc" else column.desc()
    rows = session.exec(
        select(User, _total_paid, _sites_count, _last_scan)
        .where(*conditions)
        .order_by(ordering, User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return AdminUserList(items=[_row(*r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def user_detail(user_id: int, session: Session = Depends(get_session)):
    return _detail(session, _get_user_or_404(session, user_id))


@router.post("/users/{user_id}/credits", response_model=AdminUserDetail)
def adjust_credits(
    user_id: int,
    payload: CreditAdjustRequest,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    user = _get_user_or_404(session, user_id)
    try:
        apply_credit_delta(
            session, user.id, payload.delta, CreditReason.admin, note=payload.note, actor_id=admin.id
        )
    except InsufficientCredits:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{user.email} has {user.credits_balance} credits - can't remove {abs(payload.delta)}.",
        )
    log_admin_action(session, admin.id, "credits_adjusted", user.id, {"delta": payload.delta, "note": payload.note})
    session.commit()
    session.refresh(user)
    return _detail(session, user)


@router.post("/users/{user_id}/plan", response_model=AdminUserDetail)
def change_plan(
    user_id: int,
    payload: PlanChangeRequest,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    user = _get_user_or_404(session, user_id)
    before = user.plan.value
    set_user_plan(session, user, payload.plan)
    log_admin_action(
        session, admin.id, "plan_changed", user.id, {"from": before, "to": payload.plan.value, "note": payload.note}
    )
    session.commit()
    session.refresh(user)
    return _detail(session, user)


@router.post("/users/{user_id}/payments", response_model=AdminUserDetail, status_code=status.HTTP_201_CREATED)
def record_manual_payment(
    user_id: int,
    payload: ManualPaymentRequest,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """A payment received outside Dodo (UPI, bank transfer, invoice). Can grant
    credits and/or switch the plan in the same step."""
    user = _get_user_or_404(session, user_id)
    payment, _ = record_payment(
        session,
        user=user,
        amount_cents=payload.amount_cents,
        kind=PaymentKind.manual,
        provider="manual",
        plan=payload.plan.value if payload.plan else None,
        credits=payload.credits,
        note=payload.note,
        paid_at=payload.paid_at,
        actor_id=admin.id,
    )
    if payload.plan is not None:
        set_user_plan(session, user, payload.plan)
    log_admin_action(
        session, admin.id, "payment_recorded", user.id,
        {"payment_id": payment.id, "amount_cents": payload.amount_cents, "credits": payload.credits,
         "plan": payload.plan.value if payload.plan else None, "note": payload.note},
    )
    session.commit()
    session.refresh(user)
    return _detail(session, user)


# --- pricing catalog ---

def _product_read(p: Product) -> ProductRead:
    return ProductRead(
        id=p.id, key=p.key, name=p.name, kind=p.kind, price_cents=p.price_cents, interval=p.interval,
        plan=p.plan, credits=p.credits, dodo_product_id=p.dodo_product_id, description=p.description,
        active=p.active, sort_order=p.sort_order, updated_at=p.updated_at,
    )


def _ensure_dodo_id_free(session: Session, dodo_product_id: Optional[str], own_id: Optional[int]) -> None:
    if not dodo_product_id:
        return
    other = session.exec(select(Product).where(Product.dodo_product_id == dodo_product_id)).first()
    if other is not None and other.id != own_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'That Dodo product is already linked to "{other.name}".',
        )


@router.get("/products", response_model=List[ProductRead])
def list_products(session: Session = Depends(get_session)):
    return [_product_read(p) for p in session.exec(select(Product).order_by(Product.sort_order, Product.id)).all()]


@router.put("/products/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    changes = payload.model_dump(exclude_unset=True)
    if "credits" in changes and product.kind != "credit_pack":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only credit packs have credits.")
    if "dodo_product_id" in changes:
        changes["dodo_product_id"] = (changes["dodo_product_id"] or "").strip() or None
        _ensure_dodo_id_free(session, changes["dodo_product_id"], product.id)
    if "name" in changes:
        changes["name"] = changes["name"].strip()

    before = {k: getattr(product, k) for k in changes}
    for key, value in changes.items():
        setattr(product, key, value)
    product.updated_at = datetime.utcnow()
    session.add(product)
    log_admin_action(session, admin.id, "product_updated", None, {"product": product.key, "before": before, "after": changes})
    session.commit()
    session.refresh(product)
    return _product_read(product)


@router.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_credit_pack(
    payload: ProductCreate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    if session.exec(select(Product).where(Product.key == payload.key)).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A product with that key already exists.")
    dodo_id = (payload.dodo_product_id or "").strip() or None
    _ensure_dodo_id_free(session, dodo_id, None)
    next_order = (session.exec(select(func.coalesce(func.max(Product.sort_order), 0))).one()) + 10
    product = Product(
        key=payload.key, name=payload.name.strip(), kind="credit_pack", price_cents=payload.price_cents,
        credits=payload.credits, dodo_product_id=dodo_id, description=payload.description, sort_order=next_order,
    )
    session.add(product)
    log_admin_action(session, admin.id, "product_created", None, {"product": payload.key})
    session.commit()
    session.refresh(product)
    return _product_read(product)


@router.post("/products/{product_id}/verify", response_model=ProductVerifyResult)
def verify_product(product_id: int, session: Session = Depends(get_session)):
    """Compare the price shown to visitors with what Dodo will actually charge.
    The public price is just text; the charge comes from the Dodo product, and a
    mismatch is both a support headache and a compliance problem."""
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if not product.dodo_product_id:
        return ProductVerifyResult(ok=False, message="No Dodo product linked yet - customers can't buy this.")
    if not settings.billing_enabled:
        return ProductVerifyResult(ok=False, message="Dodo API keys aren't configured on the server yet.")
    try:
        remote = dodo.get_product(product.dodo_product_id)
    except dodo.DodoError as exc:
        return ProductVerifyResult(ok=False, message=str(exc))

    price = remote.get("price") or {}
    remote_cents, currency = price.get("price"), price.get("currency")
    if remote_cents is None:
        return ProductVerifyResult(ok=False, message="Dodo returned no fixed price for that product.", dodo_currency=currency)
    if currency != "USD":
        return ProductVerifyResult(
            ok=False, message=f"Dodo product is priced in {currency}; Signal shows USD.",
            dodo_price_cents=remote_cents, dodo_currency=currency,
        )
    if remote_cents != product.price_cents:
        return ProductVerifyResult(
            ok=False,
            message=f"Mismatch: shown ${product.price_cents / 100:.2f}, Dodo charges ${remote_cents / 100:.2f}.",
            dodo_price_cents=remote_cents, dodo_currency=currency,
        )
    return ProductVerifyResult(
        ok=True, message="Matches Dodo.", dodo_price_cents=remote_cents, dodo_currency=currency
    )
