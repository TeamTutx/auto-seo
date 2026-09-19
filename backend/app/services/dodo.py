"""Dodo Payments (Merchant of Record) - thin HTTP client + webhook verification.

Plain httpx against Dodo's REST API instead of their SDK: we use three
endpoints, and the SDK's webhook helper needs an extra dependency for what is a
few lines of HMAC (the Standard Webhooks spec, https://www.standardwebhooks.com).
Field names below were checked against the official SDK's types
(dodopayments 1.117), not guessed.

Nothing here touches the database; see billing.py / dodo_webhooks.py for that.
"""
import base64
import hashlib
import hmac
import json
import time
from typing import Any, Mapping, Optional

import httpx

from app.config import settings

BASE_URLS = {
    "live_mode": "https://live.dodopayments.com",
    "test_mode": "https://test.dodopayments.com",
}

WEBHOOK_TOLERANCE_SECONDS = 300


class DodoError(Exception):
    """A call to Dodo Payments failed (or billing isn't configured)."""


class WebhookVerificationError(Exception):
    """The webhook's signature/timestamp didn't check out - reject it."""


def _request(method: str, path: str, body: Optional[dict] = None) -> dict:
    if not settings.dodo_api_key:
        raise DodoError("Billing is not configured")
    base = settings.dodo_base_url.rstrip("/") or BASE_URLS.get(settings.dodo_environment, BASE_URLS["test_mode"])
    try:
        response = httpx.request(
            method,
            f"{base}{path}",
            headers={"Authorization": f"Bearer {settings.dodo_api_key}"},
            json=body,
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise DodoError(f"Could not reach Dodo Payments: {exc}")
    if response.status_code >= 400:
        raise DodoError(f"Dodo Payments error {response.status_code}: {response.text[:200]}")
    return response.json()


def create_checkout_session(
    *,
    product_id: str,
    email: str,
    customer_id: Optional[str],
    metadata: Mapping[str, str],
    return_url: str,
    cancel_url: Optional[str] = None,
) -> str:
    """Create a hosted checkout for one unit of a product; returns its URL. An
    existing Dodo customer is reused so their saved details/subscriptions stay
    together; `metadata` (user id, product key) comes back on the payment and
    subscription webhooks, which is how we know whose money it is."""
    customer: dict = {"customer_id": customer_id} if customer_id else {"email": email}
    data = _request(
        "POST",
        "/checkouts",
        {
            "product_cart": [{"product_id": product_id, "quantity": 1}],
            "customer": customer,
            "metadata": dict(metadata),
            "return_url": return_url,
            "cancel_url": cancel_url or return_url,
        },
    )
    url = data.get("checkout_url")
    if not url:
        raise DodoError("Dodo Payments did not return a checkout URL")
    return url


def create_portal_session(customer_id: str, return_url: str) -> str:
    """One-time link to Dodo's hosted customer portal (cancel, update card)."""
    data = _request("POST", f"/customers/{customer_id}/customer-portal/session", {"return_url": return_url})
    link = data.get("link")
    if not link:
        raise DodoError("Dodo Payments did not return a portal link")
    return link


def get_product(product_id: str) -> dict:
    return _request("GET", f"/products/{product_id}")


def verify_webhook(
    payload: bytes,
    headers: Mapping[str, str],
    secret: str,
    *,
    tolerance: int = WEBHOOK_TOLERANCE_SECONDS,
    now: Optional[float] = None,
) -> Any:
    """Verify a Standard Webhooks signature and return the parsed JSON body.

    The signed content is `{webhook-id}.{webhook-timestamp}.{raw body}`, HMAC-
    SHA256'd with the base64-decoded secret (minus its `whsec_` prefix); the
    `webhook-signature` header holds one or more space-separated `v1,<base64>`
    entries. The timestamp check stops a captured request being replayed later.
    Must be given the *raw* body - re-serialising parsed JSON changes the bytes.
    """
    h = {k.lower(): v for k, v in headers.items()}
    msg_id = h.get("webhook-id")
    timestamp = h.get("webhook-timestamp")
    signatures = h.get("webhook-signature")
    if not (msg_id and timestamp and signatures):
        raise WebhookVerificationError("missing webhook headers")
    try:
        ts = int(timestamp)
    except ValueError:
        raise WebhookVerificationError("invalid webhook timestamp")
    if abs((now if now is not None else time.time()) - ts) > tolerance:
        raise WebhookVerificationError("webhook timestamp outside tolerance")

    key = secret[len("whsec_"):] if secret.startswith("whsec_") else secret
    try:
        secret_bytes = base64.b64decode(key)
    except Exception:
        raise WebhookVerificationError("webhook secret is not valid base64")

    signed_content = f"{msg_id}.{timestamp}.".encode() + payload
    expected = base64.b64encode(hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()).decode()
    for entry in signatures.split(" "):
        version, _, signature = entry.partition(",")
        if version == "v1" and hmac.compare_digest(signature, expected):
            try:
                return json.loads(payload)
            except ValueError:
                raise WebhookVerificationError("webhook body is not JSON")
    raise WebhookVerificationError("no matching signature")


def sign_webhook(payload: bytes, secret: str, msg_id: str = "msg_test", timestamp: Optional[int] = None) -> dict:
    """Build the three webhook headers for `payload` - the inverse of
    verify_webhook. Used by tests and by scripts/dodo_test_webhook.py to
    exercise the endpoint without Dodo."""
    ts = str(timestamp if timestamp is not None else int(time.time()))
    key = secret[len("whsec_"):] if secret.startswith("whsec_") else secret
    signed_content = f"{msg_id}.{ts}.".encode() + payload
    signature = base64.b64encode(hmac.new(base64.b64decode(key), signed_content, hashlib.sha256).digest()).decode()
    return {"webhook-id": msg_id, "webhook-timestamp": ts, "webhook-signature": f"v1,{signature}"}
