"""Apply verified Dodo Payments webhook events to our database.

Event and field names come from Dodo's official SDK types (dodopayments 1.117):
- payment.succeeded  -> data is a Payment (payment_id, total_amount incl. tax,
  tax, currency, settlement_*, customer, metadata, subscription_id, product_cart).
  product_cart is only filled for one-time purchases.
- refund.succeeded -> data is a Refund (refund_id, payment_id, amount, is_partial).
- subscription.* -> Signal sells one-off credit packs, so these should never
  arrive. They're logged rather than acted on (see _on_subscription).

Design rules:
- Idempotent. Dodo retries up to 8 times over ~10 hours, so every handler must
  be safe to run twice (record_payment/record_refund dedupe on the provider id;
  plan sync is naturally idempotent).
- Never make Dodo retry forever: an event we can't attribute to a user is
  logged and acknowledged (returns "unmatched"), not raised. Real errors raise,
  which the router turns into a 5xx so Dodo does retry.
- Money is recorded even when the product isn't in our catalog - it's real.
"""
import logging
from typing import Optional, Tuple

from sqlmodel import Session, func, select

from app.models import PaymentKind, Product, User
from app.services.billing import (
    find_payment,
    get_product_by_dodo_id,
    get_product_by_key,
    log_admin_action,
    record_payment,
    record_refund,
)

logger = logging.getLogger("signal.billing")


def handle_event(session: Session, event: dict) -> str:
    """Apply one event. Does not commit. Returns a short label for logs/tests."""
    event_type = event.get("type") or ""
    data = event.get("data") or {}
    if event_type == "payment.succeeded":
        return _on_payment_succeeded(session, data)
    if event_type == "refund.succeeded":
        return _on_refund(session, data)
    if event_type.startswith("subscription."):
        return _on_subscription(session, event_type, data)
    if event_type.startswith("dispute."):
        return _on_dispute(session, event_type, data)
    return "ignored"


# --- helpers ---

def _resolve_user(session: Session, data: dict) -> Optional[User]:
    """Whose is this? Preference order: the user id we put in checkout metadata
    (unforgeable by the customer), the Dodo customer id, the subscription id,
    and only then - if it matches exactly one account - the email."""
    metadata = data.get("metadata") or {}
    raw_id = metadata.get("user_id")
    if raw_id is not None:
        try:
            user = session.get(User, int(raw_id))
        except (TypeError, ValueError):
            user = None
        if user:
            return user

    customer = data.get("customer") or {}
    customer_id = customer.get("customer_id")
    if customer_id:
        user = session.exec(select(User).where(User.dodo_customer_id == customer_id)).first()
        if user:
            return user

    subscription_id = data.get("subscription_id")
    if subscription_id:
        user = session.exec(select(User).where(User.dodo_subscription_id == subscription_id)).first()
        if user:
            return user

    email = (customer.get("email") or "").strip().lower()
    if email:
        matches = session.exec(select(User).where(func.lower(User.email) == email)).all()
        if len(matches) == 1:
            return matches[0]
    return None


def _remember_customer(user: User, data: dict) -> None:
    customer_id = (data.get("customer") or {}).get("customer_id")
    if customer_id and user.dodo_customer_id != customer_id:
        user.dodo_customer_id = customer_id


def _usd_amounts(data: dict) -> Optional[Tuple[int, int]]:
    """(amount excluding tax, tax) in USD cents, or None if it can't be worked
    out. A USD charge is used as is; otherwise (Dodo's adaptive pricing charges
    the customer in their own currency) the USD settlement amounts are used."""
    if data.get("currency") == "USD" and data.get("total_amount") is not None:
        tax = data.get("tax") or 0
        return data["total_amount"] - tax, tax
    if data.get("settlement_currency") == "USD" and data.get("settlement_amount") is not None:
        tax = data.get("settlement_tax") or 0
        return data["settlement_amount"] - tax, tax
    return None


def _resolve_product(session: Session, data: dict, user: User) -> Optional[Product]:
    key = (data.get("metadata") or {}).get("product_key")
    if key:
        product = get_product_by_key(session, str(key))
        if product:
            return product
    for item in data.get("product_cart") or []:
        product = get_product_by_dodo_id(session, item.get("product_id", ""))
        if product:
            return product
    return None


# --- handlers ---

def _on_payment_succeeded(session: Session, data: dict) -> str:
    payment_id = data.get("payment_id")
    if not payment_id:
        return "ignored"
    if data.get("is_update_payment_method"):
        return "ignored"  # a card-update charge, not a sale

    user = _resolve_user(session, data)
    if user is None:
        logger.warning("Dodo payment %s could not be matched to a user; record it manually", payment_id)
        return "unmatched"

    product = _resolve_product(session, data, user)
    is_subscription = bool(data.get("subscription_id"))
    amounts = _usd_amounts(data)
    note = None
    if amounts is None:
        logger.warning("Dodo payment %s has no USD amount (currency %s)", payment_id, data.get("currency"))
        amounts = (0, 0)
        note = f"Charged in {data.get('currency')}; USD amount unavailable - check Dodo"
    elif product is None:
        note = "Dodo product not in the catalog"

    credits = 0
    if product is not None and product.kind == "credit_pack":
        quantity = sum(
            item.get("quantity", 1)
            for item in data.get("product_cart") or []
            if item.get("product_id") == product.dodo_product_id
        ) or 1
        credits = product.credits * quantity

    # Signal only sells credit packs; a payment carrying a subscription id would
    # be something set up in Dodo directly. The money is still recorded as such.
    kind = PaymentKind.subscription if is_subscription else PaymentKind.credit_pack
    payment, created = record_payment(
        session,
        user=user,
        amount_cents=amounts[0],
        tax_cents=amounts[1],
        kind=kind,
        provider="dodo",
        provider_ref=payment_id,
        product_key=product.key if product else None,
        credits=credits,
        note=note,
    )
    if not created:
        return "duplicate"

    _remember_customer(user, data)
    if data.get("subscription_id"):
        user.dodo_subscription_id = data["subscription_id"]
    session.add(user)
    log_admin_action(
        session, None, "payment_received", user.id,
        {"payment_id": payment_id, "amount_cents": amounts[0], "kind": kind.value, "credits": credits},
    )
    return "recorded"


def _on_subscription(session: Session, event_type: str, data: dict) -> str:
    """Signal has no recurring products, so there is no plan to grant or revoke.
    Anything that arrives here was created in Dodo outside Signal - record it in
    the audit log so the owner can see it, and acknowledge it so Dodo stops
    retrying. The money itself still arrives as payment.succeeded."""
    user = _resolve_user(session, data)
    if user is not None:
        _remember_customer(user, data)
        session.add(user)
    log_admin_action(
        session, None, event_type.replace(".", "_"), user.id if user else None,
        {"subscription_id": data.get("subscription_id"), "status": data.get("status"),
         "product_id": data.get("product_id")},
    )
    logger.info("Dodo %s for subscription %s - Signal sells no subscriptions", event_type, data.get("subscription_id"))
    return "subscription_logged"


def _on_refund(session: Session, data: dict) -> str:
    refund_id = data.get("refund_id")
    payment_id = data.get("payment_id")
    if not refund_id or not payment_id:
        return "ignored"

    original = find_payment(session, "dodo", payment_id)
    if original is None:
        logger.warning("Dodo refund %s is for payment %s, which we never recorded", refund_id, payment_id)
        return "unmatched"
    user = session.get(User, original.user_id)
    is_partial = bool(data.get("is_partial"))
    amount = data.get("amount") or 0

    if data.get("currency") not in (None, "USD") and is_partial:
        # Adaptive-pricing partial refund: the amount is in the customer's
        # currency, so we can't prorate it to USD safely. Flag it instead.
        log_admin_action(session, None, "refund_needs_review", user.id, {"refund_id": refund_id, "amount": amount, "currency": data.get("currency")})
        return "needs_review"

    _, created = record_refund(
        session,
        user=user,
        provider="dodo",
        provider_ref=refund_id,
        refunded_cents=amount,
        original=original,
        is_partial=is_partial,
        note=data.get("reason"),
    )
    if created:
        log_admin_action(session, None, "refund_recorded", user.id, {"refund_id": refund_id, "payment_id": payment_id, "partial": is_partial})
    return "refunded" if created else "duplicate"


def _on_dispute(session: Session, event_type: str, data: dict) -> str:
    """Chargebacks are money moving without our say-so; just surface them in the
    audit log for the owner to act on (respond in Dodo, adjust manually)."""
    original = find_payment(session, "dodo", data.get("payment_id", "")) if data.get("payment_id") else None
    log_admin_action(
        session, None, event_type.replace(".", "_"), original.user_id if original else None,
        {"dispute_id": data.get("dispute_id"), "payment_id": data.get("payment_id"), "amount": data.get("amount")},
    )
    return "dispute_logged"
