"""Shared credit-spend gate for every metered action (rank checks, AI
suggestions - REQUIREMENTS.md §3.3). Not tied to Stripe: this is just
check-balance/decrement against User.credits_balance, which already works
the same way it will once Stripe adds a way to refill that balance.
"""
from fastapi import HTTPException, status
from sqlmodel import Session

from app.models import User


def require_credits(user: User, needed: int = 1) -> None:
    if user.credits_balance < needed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Not enough credits ({user.credits_balance} remaining, {needed} needed). "
                "Credit top-ups aren't available yet (billing isn't live) - check back soon."
            ),
        )


def deduct_credit(session: Session, user: User) -> None:
    user.credits_balance -= 1
    session.add(user)
    session.commit()
