"""Credit balance changes - the only code that should write
User.credits_balance after signup (REQUIREMENTS.md §3.3).

Every change goes through apply_credit_delta(), which does two things in one
transaction: an atomic SQL update of the balance and a CreditTransaction row
recording it. The ledger therefore always sums to the balance, and spending is a
conditional UPDATE (`... WHERE credits_balance + :delta >= 0`) rather than a
read-then-write in Python - two concurrent requests can no longer both pass the
balance check and lose an update.

Not tied to any payment provider: purchases, admin top-ups and refunds are just
different `reason`s.
"""
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlmodel import Session

from app.config import settings
from app.models import CreditReason, CreditTransaction, User


class InsufficientCredits(Exception):
    """The balance would go below zero."""


def require_credits(user: User, needed: int = 1) -> None:
    if user.credits_balance < needed:
        hint = (
            "Buy more credits on the Billing page."
            if settings.billing_enabled
            else "Credit top-ups aren't available yet (billing isn't live) - check back soon."
        )
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Not enough credits ({user.credits_balance} remaining, {needed} needed). {hint}",
        )


def apply_credit_delta(
    session: Session,
    user_id: int,
    delta: int,
    reason: CreditReason,
    *,
    ref: Optional[str] = None,
    note: Optional[str] = None,
    actor_id: Optional[int] = None,
    allow_negative: bool = False,
) -> int:
    """Add `delta` (may be negative) to a user's balance and record it. Returns
    the new balance. Does NOT commit - the caller commits, so this can be one
    step of a larger transaction (e.g. record_payment). Raises
    InsufficientCredits if the balance would go below zero (unless
    allow_negative)."""
    if delta == 0:
        raise ValueError("credit delta must be non-zero")

    session.flush()  # don't let the update below race pending changes on this session
    stmt = (
        update(User)
        .where(User.id == user_id)
        .values(credits_balance=User.credits_balance + delta)
        .execution_options(synchronize_session=False)
    )
    if not allow_negative:
        stmt = stmt.where(User.credits_balance + delta >= 0)
    result = session.execute(stmt)
    if result.rowcount == 0:
        if session.get(User, user_id) is None:
            raise ValueError(f"no such user: {user_id}")
        raise InsufficientCredits()

    user = session.get(User, user_id)
    session.refresh(user)  # same transaction, so this sees the row we just locked and updated
    session.add(
        CreditTransaction(
            user_id=user_id,
            delta=delta,
            balance_after=user.credits_balance,
            reason=reason.value,
            ref=ref,
            note=note,
            actor_id=actor_id,
        )
    )
    return user.credits_balance


def deduct_credit(session: Session, user: User, ref: Optional[str] = None) -> None:
    """Spend one credit after the metered work has succeeded (never charge on
    failure). `ref` records what it was spent on, e.g. "keyword_check"."""
    try:
        apply_credit_delta(session, user.id, -1, CreditReason.usage, ref=ref)
    except InsufficientCredits:
        session.rollback()
        # Another request spent the last credit between our balance check and now.
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Not enough credits - another request just used your last one.",
        )
    session.commit()
    session.refresh(user)
