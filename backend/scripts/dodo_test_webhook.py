#!/usr/bin/env python
"""Send a correctly *signed* fake Dodo Payments webhook to a Signal backend, to
test the billing flow end to end without making a real purchase.

    export DODO_WEBHOOK_KEY=whsec_...        # the same secret the server has
    python scripts/dodo_test_webhook.py http://localhost:8000 payment --user-id 1 --product-key credits_50
    python scripts/dodo_test_webhook.py http://localhost:8000 subscription --user-id 1 --product-id pdt_pro --status active
    python scripts/dodo_test_webhook.py http://localhost:8000 subscription --user-id 1 --product-id pdt_pro --status expired
    python scripts/dodo_test_webhook.py http://localhost:8000 refund --payment-id pay_demo_1 --amount-cents 900

Against a real deployment this DOES change that user's credits/plan/payments -
it's the same code path a genuine payment takes. Payload shapes follow Dodo's
official SDK types (see app/services/dodo_webhooks.py).
"""
import argparse
import json
import os
import sys
import time
import uuid

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.services.dodo import sign_webhook  # noqa: E402


def build_event(args) -> dict:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    customer = {"customer_id": args.customer_id, "email": args.email, "name": "Test Customer"}
    if args.kind == "payment":
        total = args.amount_cents + args.tax_cents
        data = {
            "payment_id": args.payment_id or f"pay_{uuid.uuid4().hex[:12]}",
            "status": "succeeded", "currency": "USD", "total_amount": total, "tax": args.tax_cents,
            "settlement_currency": "USD", "settlement_amount": total, "settlement_tax": args.tax_cents,
            "customer": customer, "is_update_payment_method": False, "retry_attempt": 0,
            "metadata": {"user_id": str(args.user_id), **({"product_key": args.product_key} if args.product_key else {})},
            "product_cart": None, "subscription_id": args.subscription_id,
        }
        return {"business_id": "bus_test", "type": "payment.succeeded", "timestamp": now, "data": data}
    if args.kind == "subscription":
        data = {
            "subscription_id": args.subscription_id or "sub_demo_1", "status": args.status,
            "product_id": args.product_id, "customer": customer, "metadata": {"user_id": str(args.user_id)},
        }
        return {"business_id": "bus_test", "type": f"subscription.{args.status}", "timestamp": now, "data": data}
    data = {
        "refund_id": args.refund_id or f"ref_{uuid.uuid4().hex[:12]}", "payment_id": args.payment_id,
        "amount": args.amount_cents, "currency": "USD", "is_partial": args.partial, "status": "succeeded",
        "reason": "test", "customer": customer, "metadata": {},
    }
    return {"business_id": "bus_test", "type": "refund.succeeded", "timestamp": now, "data": data}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base_url")
    parser.add_argument("kind", choices=["payment", "subscription", "refund"])
    parser.add_argument("--user-id", type=int)
    parser.add_argument("--product-key", help="catalog key, e.g. credits_50 or pro")
    parser.add_argument("--product-id", help="Dodo product id (subscription events)")
    parser.add_argument("--status", default="active", help="subscription status: active, expired, cancelled, ...")
    parser.add_argument("--amount-cents", type=int, default=900)
    parser.add_argument("--tax-cents", type=int, default=0)
    parser.add_argument("--payment-id")
    parser.add_argument("--refund-id")
    parser.add_argument("--subscription-id")
    parser.add_argument("--partial", action="store_true")
    parser.add_argument("--customer-id", default="cus_test_1")
    parser.add_argument("--email", default="customer@example.com")
    args = parser.parse_args()

    secret = os.environ.get("DODO_WEBHOOK_KEY")
    if not secret:
        sys.exit("Set DODO_WEBHOOK_KEY to the server's webhook signing secret.")
    if args.kind in ("payment", "subscription") and args.user_id is None:
        sys.exit("--user-id is required")
    if args.kind == "refund" and not args.payment_id:
        sys.exit("--payment-id is required for a refund")

    body = json.dumps(build_event(args)).encode()
    response = httpx.post(
        f"{args.base_url.rstrip('/')}/webhooks/dodo", content=body, headers=sign_webhook(body, secret), timeout=30
    )
    print(response.status_code, response.text)


if __name__ == "__main__":
    main()
