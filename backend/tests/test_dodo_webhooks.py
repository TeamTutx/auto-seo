"""Payloads mirror Dodo's official SDK types (dodopayments 1.117): a Payment has
total_amount (incl. tax), tax, currency, settlement_*, customer, metadata,
subscription_id and - for one-time purchases only - product_cart."""
import base64
import json
import time

import pytest
from sqlmodel import Session, select

import app.services.billing as billing_service
from app.models import AdminAuditLog, CreditTransaction, Payment, PaymentKind, User
from app.services.dodo import sign_webhook
from tests.conftest import WEBHOOK_SECRET, get_user, link_dodo_product, register_and_login


# --- factories ---

def payment_event(payment_id="pay_1", *, user_id=None, product_key=None, customer_id="cus_1", email="buyer@test.dev",
                  total=500, tax=0, currency="USD", cart=None, subscription_id=None, **extra):
    metadata = {}
    if user_id is not None:
        metadata["user_id"] = str(user_id)
    if product_key:
        metadata["product_key"] = product_key
    data = {
        "payment_id": payment_id, "status": "succeeded", "currency": currency, "total_amount": total, "tax": tax,
        "settlement_currency": "USD", "settlement_amount": total, "settlement_tax": tax,
        "customer": {"customer_id": customer_id, "email": email, "name": "Buyer"},
        "metadata": metadata, "product_cart": cart, "subscription_id": subscription_id,
        "is_update_payment_method": False, "retry_attempt": 0,
    }
    data.update(extra)
    return {"business_id": "bus_1", "type": "payment.succeeded", "timestamp": "2026-09-19T10:00:00Z", "data": data}


def subscription_event(event_type="subscription.active", *, subscription_id="sub_1", status="active", product_id="pdt_x",
                       user_id=None, customer_id="cus_1", email="buyer@test.dev"):
    return {
        "business_id": "bus_1", "type": event_type, "timestamp": "2026-09-19T10:00:00Z",
        "data": {
            "subscription_id": subscription_id, "status": status, "product_id": product_id,
            "customer": {"customer_id": customer_id, "email": email, "name": "Buyer"},
            "metadata": {"user_id": str(user_id)} if user_id is not None else {},
        },
    }


def refund_event(refund_id="ref_1", payment_id="pay_1", amount=500, is_partial=False, currency="USD"):
    return {
        "business_id": "bus_1", "type": "refund.succeeded", "timestamp": "2026-09-19T11:00:00Z",
        "data": {"refund_id": refund_id, "payment_id": payment_id, "amount": amount, "currency": currency,
                 "is_partial": is_partial, "status": "succeeded", "reason": "requested_by_customer",
                 "customer": {"customer_id": "cus_1", "email": "buyer@test.dev", "name": "Buyer"}, "metadata": {}},
    }


def post(client, event, secret=WEBHOOK_SECRET, **sign_kwargs):
    body = json.dumps(event).encode()
    return client.post("/webhooks/dodo", content=body, headers=sign_webhook(body, secret, **sign_kwargs))


def payments(db):
    with Session(db) as session:
        return session.exec(select(Payment).order_by(Payment.id)).all()


def ledger(db, user_id):
    with Session(db) as session:
        return session.exec(select(CreditTransaction).where(CreditTransaction.user_id == user_id).order_by(CreditTransaction.id)).all()


@pytest.fixture
def buyer(client, db, products, billing_on):
    register_and_login(client, "buyer@test.dev")
    link_dodo_product(db, "credits_50", "pdt_credits")
    link_dodo_product(db, "credits_200", "pdt_big")
    return get_user(db, "buyer@test.dev")


# --- endpoint + signature ---

def test_webhook_is_503_until_billing_is_configured(client):
    assert post(client, payment_event()).status_code == 503


def test_unsigned_forged_stale_or_tampered_webhooks_are_rejected_and_change_nothing(client, db, buyer):
    event = payment_event(user_id=buyer.id, product_key="credits_50")
    body = json.dumps(event).encode()

    no_headers = client.post("/webhooks/dodo", content=body)
    wrong_secret = post(client, event, secret="whsec_" + base64.b64encode(b"z" * 24).decode())
    stale = post(client, event, timestamp=int(time.time()) - 3600)
    tampered = client.post("/webhooks/dodo", content=body.replace(b"500", b"5000000"), headers=sign_webhook(body, WEBHOOK_SECRET))
    not_json = client.post("/webhooks/dodo", content=b"not json", headers=sign_webhook(b"not json", WEBHOOK_SECRET))

    assert [r.status_code for r in (no_headers, wrong_secret, stale, tampered, not_json)] == [400] * 5
    assert payments(db) == [] and get_user(db, "buyer@test.dev").credits_balance == 3


def test_unknown_event_types_are_acknowledged(client, buyer):
    resp = post(client, {"type": "license_key.created", "data": {}})
    assert resp.status_code == 200 and resp.json() == {"received": True, "result": "ignored"}


# --- credit pack purchase ---

def test_a_credit_pack_purchase_grants_credits_and_records_the_payment(client, db, buyer):
    event = payment_event(user_id=buyer.id, total=550, tax=50, cart=[{"product_id": "pdt_credits", "quantity": 1}])

    resp = post(client, event)

    assert resp.status_code == 200 and resp.json()["result"] == "recorded"
    user = get_user(db, "buyer@test.dev")
    assert user.credits_balance == 53 and user.dodo_customer_id == "cus_1"
    (payment,) = payments(db)
    assert (payment.amount_cents, payment.tax_cents, payment.kind, payment.provider, payment.provider_ref) == (500, 50, "credit_pack", "dodo", "pay_1")
    assert payment.credits_granted == 50 and payment.product_key == "credits_50"
    last = ledger(db, user.id)[-1]
    assert (last.delta, last.reason, last.ref, last.balance_after) == (50, "purchase", f"payment:{payment.id}", 53)
    with Session(db) as session:
        log = session.exec(select(AdminAuditLog).where(AdminAuditLog.action == "payment_received")).one()
        assert log.actor_id is None and log.target_user_id == user.id


def test_redelivered_webhooks_do_not_grant_credits_twice(client, db, buyer):
    event = payment_event(user_id=buyer.id, cart=[{"product_id": "pdt_credits", "quantity": 1}])

    first, second, third = post(client, event), post(client, event, msg_id="msg_retry_1"), post(client, event, msg_id="msg_retry_2")

    assert [r.json()["result"] for r in (first, second, third)] == ["recorded", "duplicate", "duplicate"]
    assert get_user(db, "buyer@test.dev").credits_balance == 53
    assert len(payments(db)) == 1


def test_quantity_multiplies_the_credits(client, db, buyer):
    post(client, payment_event(user_id=buyer.id, total=1000, cart=[{"product_id": "pdt_credits", "quantity": 2}]))
    assert get_user(db, "buyer@test.dev").credits_balance == 103


def test_product_key_in_metadata_identifies_the_product_without_a_cart(client, db, buyer):
    post(client, payment_event(user_id=buyer.id, product_key="credits_50"))
    assert get_user(db, "buyer@test.dev").credits_balance == 53


# --- subscriptions (Signal doesn't sell any) ---

def test_a_subscription_event_is_logged_but_grants_nothing(client, db, buyer):
    """Signal sells one-off credit packs. A subscription event could only come
    from something set up in Dodo directly, so it's surfaced to the owner and
    acknowledged - never acted on."""
    resp = post(client, subscription_event(user_id=buyer.id))

    assert resp.status_code == 200 and resp.json()["result"] == "subscription_logged"
    user = get_user(db, "buyer@test.dev")
    assert user.credits_balance == 3 and payments(db) == []
    assert user.dodo_customer_id == "cus_1"  # still worth remembering who they are
    with Session(db) as session:
        log = session.exec(select(AdminAuditLog).where(AdminAuditLog.action == "subscription_active")).one()
        assert log.target_user_id == user.id and json.loads(log.payload)["subscription_id"] == "sub_1"


@pytest.mark.parametrize("status", ["expired", "cancelled", "on_hold", "past_due"])
def test_no_subscription_status_can_take_credits_away(client, db, buyer, status):
    post(client, payment_event(user_id=buyer.id, product_key="credits_50"))

    resp = post(client, subscription_event(f"subscription.{status}", status=status, user_id=buyer.id))

    assert resp.json()["result"] == "subscription_logged"
    assert get_user(db, "buyer@test.dev").credits_balance == 53  # credits are bought, not rented


def test_money_arriving_with_a_subscription_id_is_still_recorded(client, db, buyer):
    resp = post(client, payment_event(user_id=buyer.id, total=2400, subscription_id="sub_1"))

    assert resp.json()["result"] == "recorded"
    (payment,) = payments(db)
    assert (payment.kind, payment.amount_cents, payment.credits_granted) == ("subscription", 2400, 0)
    assert get_user(db, "buyer@test.dev").dodo_subscription_id == "sub_1"


# --- who does this belong to? ---

def test_metadata_user_id_beats_a_misleading_email(client, db, buyer):
    register_and_login(client, "impostor@test.dev")

    post(client, payment_event(user_id=buyer.id, email="impostor@test.dev", product_key="credits_50"))

    assert get_user(db, "buyer@test.dev").credits_balance == 53
    assert get_user(db, "impostor@test.dev").credits_balance == 3


def test_falls_back_to_the_dodo_customer_id_then_a_unique_email(client, db, buyer):
    post(client, payment_event(user_id=buyer.id, product_key="credits_50"))  # learns cus_1

    by_customer = post(client, payment_event("pay_2", email="other@card.com", product_key="credits_50"))
    by_email = post(client, payment_event("pay_3", customer_id="cus_new", email="BUYER@test.dev", product_key="credits_50"))

    assert by_customer.json()["result"] == "recorded" and by_email.json()["result"] == "recorded"
    assert get_user(db, "buyer@test.dev").credits_balance == 3 + 150


def test_unattributable_payments_are_acknowledged_but_not_recorded(client, db, buyer):
    resp = post(client, payment_event(customer_id="cus_x", email="nobody@nowhere.com", product_key="credits_50"))

    assert resp.status_code == 200 and resp.json()["result"] == "unmatched"  # 200: don't make Dodo retry forever
    assert payments(db) == [] and get_user(db, "buyer@test.dev").credits_balance == 3


# --- amounts and edge cases ---

def test_adaptive_pricing_uses_the_usd_settlement_amounts(client, db, buyer):
    event = payment_event(user_id=buyer.id, product_key="credits_50", currency="EUR", total=460, tax=70,
                          settlement_amount=550, settlement_tax=50)

    post(client, event)

    (payment,) = payments(db)
    assert (payment.amount_cents, payment.tax_cents) == (500, 50)


def test_a_payment_with_no_usd_amount_is_still_recorded_and_flagged(client, db, buyer):
    event = payment_event(user_id=buyer.id, product_key="credits_50", currency="EUR", total=460, settlement_currency="EUR")

    post(client, event)

    (payment,) = payments(db)
    assert payment.amount_cents == 0 and "EUR" in payment.note
    assert get_user(db, "buyer@test.dev").credits_balance == 53  # they did pay - credits are granted


def test_money_for_a_product_not_in_the_catalog_is_still_recorded(client, db, buyer):
    post(client, payment_event(user_id=buyer.id, cart=[{"product_id": "pdt_mystery", "quantity": 1}]))

    (payment,) = payments(db)
    assert payment.amount_cents == 500 and payment.credits_granted == 0 and "catalog" in payment.note
    assert payment.product_key is None
    assert get_user(db, "buyer@test.dev").credits_balance == 3


def test_card_update_charges_and_failed_payments_are_not_sales(client, db, buyer):
    update = payment_event(user_id=buyer.id, product_key="credits_50", total=0, is_update_payment_method=True)
    failed = {**payment_event("pay_f", user_id=buyer.id, product_key="credits_50"), "type": "payment.failed"}

    assert post(client, update).json()["result"] == "ignored"
    assert post(client, failed).json()["result"] == "ignored"
    assert payments(db) == []


# --- refunds ---

def _buy_pack(client, buyer):
    post(client, payment_event(user_id=buyer.id, total=550, tax=50, cart=[{"product_id": "pdt_credits", "quantity": 1}]))


def test_a_full_refund_reverses_the_revenue_and_takes_back_the_credits(client, db, buyer):
    _buy_pack(client, buyer)

    resp = post(client, refund_event(amount=550))

    assert resp.json()["result"] == "refunded"
    rows = payments(db)
    assert [(p.kind, p.amount_cents, p.tax_cents) for p in rows] == [("credit_pack", 500, 50), ("refund", -500, -50)]
    assert sum(p.amount_cents for p in rows) == 0
    user = get_user(db, "buyer@test.dev")
    assert user.credits_balance == 3
    assert ledger(db, user.id)[-1].reason == "refund" and ledger(db, user.id)[-1].delta == -50


def test_a_refund_never_takes_more_credits_than_the_user_has_left(client, db, buyer):
    _buy_pack(client, buyer)
    with Session(db) as session:
        u = session.get(User, buyer.id)
        u.credits_balance = 10  # spent 43 of the 53
        session.add(u)
        session.commit()

    post(client, refund_event(amount=550))

    assert get_user(db, "buyer@test.dev").credits_balance == 0  # not negative


def test_a_partial_refund_is_prorated_by_tax_and_leaves_credits_alone(client, db, buyer):
    _buy_pack(client, buyer)

    post(client, refund_event(amount=275, is_partial=True))  # half of the $5.50 charged

    refund = payments(db)[1]
    assert (refund.amount_cents, refund.tax_cents) == (-250, -25)
    assert get_user(db, "buyer@test.dev").credits_balance == 53


def test_a_redelivered_refund_is_only_applied_once(client, db, buyer):
    _buy_pack(client, buyer)

    results = [post(client, refund_event(), msg_id=f"m{i}").json()["result"] for i in range(3)]

    assert results == ["refunded", "duplicate", "duplicate"]
    assert len(payments(db)) == 2 and get_user(db, "buyer@test.dev").credits_balance == 3


def test_a_refund_for_a_payment_we_never_recorded_is_acknowledged(client, db, buyer):
    resp = post(client, refund_event(payment_id="pay_unknown"))
    assert resp.status_code == 200 and resp.json()["result"] == "unmatched" and payments(db) == []


def test_a_partial_refund_in_another_currency_is_flagged_not_guessed(client, db, buyer):
    _buy_pack(client, buyer)

    resp = post(client, refund_event(amount=400, is_partial=True, currency="EUR"))

    assert resp.json()["result"] == "needs_review" and len(payments(db)) == 1


def test_disputes_are_logged_for_the_owner(client, db, buyer):
    _buy_pack(client, buyer)
    event = {"type": "dispute.opened", "data": {"dispute_id": "dp_1", "payment_id": "pay_1", "amount": "550"}}

    assert post(client, event).json()["result"] == "dispute_logged"

    with Session(db) as session:
        log = session.exec(select(AdminAuditLog).where(AdminAuditLog.action == "dispute_opened")).one()
        assert log.target_user_id == buyer.id and json.loads(log.payload)["dispute_id"] == "dp_1"


# --- robustness ---

def test_a_processing_error_returns_5xx_and_leaves_no_partial_state(client, db, buyer, monkeypatch):
    import app.services.dodo_webhooks as handlers

    def explode(*a, **k):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(handlers, "record_payment", explode)

    resp = post(client, payment_event(user_id=buyer.id, product_key="credits_50"))

    assert resp.status_code == 500  # so Dodo retries
    assert payments(db) == [] and get_user(db, "buyer@test.dev").credits_balance == 3


def test_losing_the_insert_race_to_a_concurrent_delivery_is_treated_as_a_duplicate(client, db, buyer, monkeypatch):
    """Two deliveries of the same event both pass the 'already recorded?' check;
    the unique constraint makes the second insert fail - it must resolve to the
    existing row without granting credits again."""
    user_id = buyer.id
    with Session(db) as session:
        first, created = billing_service.record_payment(
            session, user=session.get(User, user_id), amount_cents=500, kind=PaymentKind.credit_pack,
            provider="dodo", provider_ref="pay_race", credits=50,
        )
        first_id = first.id
        session.commit()
        assert created

    real_find = billing_service.find_payment
    calls = {"n": 0}

    def blind_first_time(session, provider, ref):
        calls["n"] += 1
        return None if calls["n"] == 1 else real_find(session, provider, ref)

    monkeypatch.setattr(billing_service, "find_payment", blind_first_time)
    with Session(db) as session:
        again, created = billing_service.record_payment(
            session, user=session.get(User, user_id), amount_cents=500, kind=PaymentKind.credit_pack,
            provider="dodo", provider_ref="pay_race", credits=50,
        )
        again_id = again.id
        session.commit()

    assert created is False and again_id == first_id
    assert len(payments(db)) == 1 and get_user(db, "buyer@test.dev").credits_balance == 53
