"""Recording money and plan changes. Provider-agnostic: manual payments entered
in the admin panel and Dodo webhooks (app/services/dodo_webhooks.py) both come
through record_payment()/record_refund(), so revenue, credit grants and the
audit trail behave identically however the money arrived.

None of these functions commit - the caller owns the transaction, so a payment,
the credits it grants and the plan change land together or not at all.
"""
import json
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from app.models import (
    AdminAuditLog,
    CreditReason,
    Payment,
    PaymentKind,
    PlanTier,
    Product,
    User,
)
from app.services.credits import apply_credit_delta


def log_admin_action(
    session: Session,
    actor_id: Optional[int],
    action: str,
    target_user_id: Optional[int] = None,
    payload: Optional[dict] = None,
) -> None:
    """actor_id None means the system itself (e.g. a payment webhook)."""
    session.add(
        AdminAuditLog(
            actor_id=actor_id,
            action=action,
            target_user_id=target_user_id,
            payload=json.dumps(payload, default=str) if payload else None,
        )
    )


def set_user_plan(session: Session, user: User, plan: PlanTier) -> bool:
    """Returns True if the plan actually changed."""
    if user.plan == plan:
        return False
    user.plan = plan
    session.add(user)
    return True


def get_product_by_key(session: Session, key: str) -> Optional[Product]:
    return session.exec(select(Product).where(Product.key == key)).first()


def get_product_by_dodo_id(session: Session, dodo_product_id: str) -> Optional[Product]:
    return session.exec(select(Product).where(Product.dodo_product_id == dodo_product_id)).first()


def find_payment(session: Session, provider: str, provider_ref: str) -> Optional[Payment]:
    return session.exec(
        select(Payment).where(Payment.provider == provider, Payment.provider_ref == provider_ref)
    ).first()


def record_payment(
    session: Session,
    *,
    user: User,
    amount_cents: int,
    kind: PaymentKind,
    provider: str,
    provider_ref: Optional[str] = None,
    tax_cents: int = 0,
    plan: Optional[str] = None,
    credits: int = 0,
    note: Optional[str] = None,
    paid_at: Optional[datetime] = None,
    actor_id: Optional[int] = None,
) -> Tuple[Payment, bool]:
    """Record money received and grant any credits it bought. Idempotent on
    (provider, provider_ref): payment webhooks are retried, so a repeat delivery
    returns the existing row and (payment, False) without granting twice.
    Returns (payment, created)."""
    if provider_ref:
        existing = find_payment(session, provider, provider_ref)
        if existing:
            return existing, False

    payment = Payment(
        user_id=user.id,
        amount_cents=amount_cents,
        tax_cents=tax_cents,
        kind=kind.value,
        plan=plan,
        credits_granted=credits,
        provider=provider,
        provider_ref=provider_ref,
        note=note,
        actor_id=actor_id,
        paid_at=paid_at or datetime.utcnow(),
    )
    try:
        # A savepoint, so losing a race to a concurrent delivery of the same
        # webhook (unique constraint) doesn't poison the outer transaction.
        with session.begin_nested():
            session.add(payment)
            session.flush()
    except IntegrityError:
        existing = find_payment(session, provider, provider_ref) if provider_ref else None
        if existing is None:
            raise
        return existing, False

    if credits > 0:
        apply_credit_delta(
            session,
            user.id,
            credits,
            CreditReason.admin if provider == "manual" else CreditReason.purchase,
            ref=f"payment:{payment.id}",
            note=note,
            actor_id=actor_id,
        )
    return payment, True


def record_refund(
    session: Session,
    *,
    user: User,
    provider: str,
    provider_ref: str,
    refunded_cents: int,
    original: Optional[Payment],
    is_partial: bool,
    note: Optional[str] = None,
) -> Tuple[Payment, bool]:
    """Record a refund as a negative payment row. `refunded_cents` is what the
    provider says went back to the customer (tax included). For a full refund
    the original net amount is reversed exactly; for a partial one it's
    prorated by the original's tax share. A full refund of a credit pack also
    takes back the credits it granted - but never more than the user still has
    (we don't claw a balance below zero). Idempotent on provider_ref."""
    existing = find_payment(session, provider, provider_ref)
    if existing:
        return existing, False

    if original is not None and not is_partial:
        net = original.amount_cents
        tax = original.tax_cents
    elif original is not None and (original.amount_cents + original.tax_cents) > 0:
        gross = original.amount_cents + original.tax_cents
        net = round(refunded_cents * original.amount_cents / gross)
        tax = refunded_cents - net
    else:
        net, tax = refunded_cents, 0

    payment = Payment(
        user_id=user.id,
        amount_cents=-net,
        tax_cents=-tax,
        kind=PaymentKind.refund.value,
        plan=original.plan if original else None,
        credits_granted=0,
        provider=provider,
        provider_ref=provider_ref,
        note=note,
    )
    try:
        with session.begin_nested():
            session.add(payment)
            session.flush()
    except IntegrityError:
        existing = find_payment(session, provider, provider_ref)
        if existing is None:
            raise
        return existing, False

    if original is not None and not is_partial and original.credits_granted > 0:
        session.refresh(user)
        revoke = min(original.credits_granted, user.credits_balance)
        if revoke > 0:
            apply_credit_delta(
                session,
                user.id,
                -revoke,
                CreditReason.refund,
                ref=f"payment:{original.id}",
                note="Credits taken back after a full refund",
            )
    return payment, True


# The draft catalog from docs/REQUIREMENTS.md §3.2. Migration 0008 seeds the same
# rows for real databases; this covers databases built with create_all() (local
# dev, which has no migration history) so /pricing is never missing its paid
# plans. It only ever runs against an *empty* table, so it can't undo an admin's
# edits.
DEFAULT_PRODUCTS = [
    dict(key="pro", name="Pro", kind="subscription", price_cents=2400, interval="month", plan="pro", sort_order=10),
    dict(key="agency", name="Agency", kind="subscription", price_cents=8900, interval="month", plan="agency", sort_order=20),
    dict(
        key="credits_50", name="50 credits", kind="credit_pack", price_cents=900, credits=50,
        description="For extra rank checks and AI fixes", sort_order=30,
    ),
]


def seed_default_products(session: Session) -> int:
    """Insert the default catalog if there are no products at all. Returns rows added."""
    if session.exec(select(func.count(Product.id))).one() > 0:
        return 0
    session.add_all(Product(**row) for row in DEFAULT_PRODUCTS)
    session.commit()
    return len(DEFAULT_PRODUCTS)
