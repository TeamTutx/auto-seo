"""Public pricing - what the landing page's Plans section renders. Driven by the
Product table, so the owner edits prices from /admin/pricing instead of
redeploying. Deliberately unauthenticated (it's a marketing page)."""
from typing import List

from fastapi import APIRouter, Depends, Response
from sqlmodel import Session, select

from app.config import settings
from app.database import get_session
from app.models import PLAN_LIMITS, PlanTier, Product
from app.schemas import PlanLimitsRead, PricingCreditPack, PricingPlan, PricingResponse

router = APIRouter(tags=["pricing"])

# The free tier isn't a product (nothing to buy); its copy lives here.
FREE_PLAN = PricingPlan(
    key="free",
    name="Free",
    price_cents=0,
    interval=None,
    description=None,
    limits=PlanLimitsRead(**PLAN_LIMITS[PlanTier.free]),
    product_key=None,
    purchasable=False,
)


def build_pricing(session: Session) -> PricingResponse:
    products = session.exec(
        select(Product).where(Product.active == True).order_by(Product.sort_order, Product.id)  # noqa: E712
    ).all()
    plans: List[PricingPlan] = [FREE_PLAN]
    packs: List[PricingCreditPack] = []
    for p in products:
        purchasable = settings.billing_enabled and bool(p.dodo_product_id)
        if p.kind == "subscription" and p.plan:
            plans.append(
                PricingPlan(
                    key=p.plan,
                    name=p.name,
                    price_cents=p.price_cents,
                    interval=p.interval,
                    description=p.description,
                    limits=PlanLimitsRead(**PLAN_LIMITS[PlanTier(p.plan)]),
                    product_key=p.key,
                    purchasable=purchasable,
                )
            )
        elif p.kind == "credit_pack":
            packs.append(
                PricingCreditPack(
                    key=p.key,
                    name=p.name,
                    price_cents=p.price_cents,
                    credits=p.credits,
                    description=p.description,
                    purchasable=purchasable,
                )
            )
    return PricingResponse(billing_enabled=settings.billing_enabled, plans=plans, credit_packs=packs)


@router.get("/pricing", response_model=PricingResponse)
def get_pricing(response: Response, session: Session = Depends(get_session)):
    # Short shared cache: it's fetched by every landing-page render.
    response.headers["Cache-Control"] = "public, max-age=60"
    return build_pricing(session)
