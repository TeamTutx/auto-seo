"""Signed-in user billing: buy a plan or credits (hosted Dodo checkout), manage
a subscription (Dodo's customer portal), and see payment history. What actually
grants the plan/credits is the webhook (app/routers/webhooks.py), never these
endpoints - a redirect back from checkout proves nothing."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.config import settings
from app.database import get_session
from app.deps import get_current_user
from app.models import Payment, PlanTier, User
from app.schemas import (
    BillingPaymentRead,
    BillingSummary,
    CheckoutRequest,
    CheckoutResponse,
    PortalResponse,
)
from app.services import dodo
from app.services.billing import get_product_by_key

router = APIRouter(tags=["billing"])


def _has_subscription(user: User) -> bool:
    return bool(user.dodo_subscription_id) and user.plan != PlanTier.free


def _billing_url(path: str = "") -> str:
    return f"{settings.frontend_url.rstrip('/')}/dashboard/billing{path}"


@router.get("/billing", response_model=BillingSummary)
def billing_summary(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    payments = session.exec(
        select(Payment).where(Payment.user_id == current_user.id).order_by(Payment.paid_at.desc(), Payment.id.desc()).limit(25)
    ).all()
    return BillingSummary(
        plan=current_user.plan,
        credits_balance=current_user.credits_balance,
        billing_enabled=settings.billing_enabled,
        has_subscription=_has_subscription(current_user),
        can_manage_billing=settings.billing_enabled and bool(current_user.dodo_customer_id),
        payments=[
            BillingPaymentRead(
                id=p.id, amount_cents=p.amount_cents, kind=p.kind, plan=p.plan,
                credits_granted=p.credits_granted, paid_at=p.paid_at,
            )
            for p in payments
        ],
    )


@router.post("/billing/checkout", response_model=CheckoutResponse)
def start_checkout(
    payload: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not settings.billing_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing isn't available yet.")

    product = get_product_by_key(session, payload.product_key)
    if product is None or not product.active or not product.dodo_product_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That product isn't available.")
    if product.kind == "subscription" and _has_subscription(current_user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a subscription. Change or cancel it from Manage subscription.",
        )

    try:
        url = dodo.create_checkout_session(
            product_id=product.dodo_product_id,
            email=current_user.email,
            customer_id=current_user.dodo_customer_id,
            # Comes back on the webhooks - this is how the payment finds its user.
            metadata={"user_id": str(current_user.id), "product_key": product.key},
            return_url=_billing_url("?checkout=success"),
            cancel_url=_billing_url("?checkout=cancelled"),
        )
    except dodo.DodoError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return CheckoutResponse(checkout_url=url)


@router.post("/billing/portal", response_model=PortalResponse)
def open_portal(current_user: User = Depends(get_current_user)):
    if not settings.billing_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing isn't available yet.")
    if not current_user.dodo_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You don't have a billing account yet - it's created with your first purchase.",
        )
    try:
        return PortalResponse(url=dodo.create_portal_session(current_user.dodo_customer_id, _billing_url()))
    except dodo.DodoError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
