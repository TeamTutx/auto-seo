"""Public pricing - what the landing page's Plans section renders. Signal sells
credits and nothing else, so this is the Product table's active credit packs in
sort order, however many the owner has created in /admin/pricing. Deliberately
unauthenticated (it's a marketing page)."""
from fastapi import APIRouter, Depends, Response
from sqlmodel import Session, select

from app.config import settings
from app.database import get_session
from app.models import ACCOUNT_LIMITS, SIGNUP_CREDITS, Product
from app.schemas import AccountLimitsRead, PricingCreditPack, PricingResponse

router = APIRouter(tags=["pricing"])


def build_pricing(session: Session) -> PricingResponse:
    products = session.exec(
        select(Product)
        .where(Product.active == True, Product.kind == "credit_pack")  # noqa: E712
        .order_by(Product.sort_order, Product.id)
    ).all()
    return PricingResponse(
        billing_enabled=settings.billing_enabled,
        signup_credits=SIGNUP_CREDITS,
        limits=AccountLimitsRead(**ACCOUNT_LIMITS),
        credit_packs=[
            PricingCreditPack(
                key=p.key,
                name=p.name,
                price_cents=p.price_cents,
                credits=p.credits,
                description=p.description,
                badge=p.badge,
                # Shown as "$0.04 / credit" so visitors can compare packs without
                # doing the arithmetic. Rounded here so every client agrees.
                price_per_credit_cents=round(p.price_cents / p.credits, 2) if p.credits else None,
                purchasable=settings.billing_enabled and bool(p.dodo_product_id),
            )
            for p in products
        ],
    )


@router.get("/pricing", response_model=PricingResponse)
def get_pricing(response: Response, session: Session = Depends(get_session)):
    # Short shared cache: it's fetched by every landing-page render.
    response.headers["Cache-Control"] = "public, max-age=60"
    return build_pricing(session)
