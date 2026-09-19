import httpx
import pytest
from sqlmodel import Session, select

from app.models import Payment, PaymentKind, User
from app.services import dodo
from tests.conftest import get_user, link_dodo_product, register_and_login


@pytest.fixture
def dodo_calls(monkeypatch):
    """Capture (method, path, body) of every call to Dodo and answer like it would."""
    calls = []

    def fake_request(method, path, body=None):
        calls.append((method, path, body))
        if path == "/checkouts":
            return {"session_id": "cks_1", "checkout_url": "https://checkout.dodo.test/cks_1"}
        if "customer-portal" in path:
            return {"link": "https://portal.dodo.test/abc"}
        raise AssertionError(f"unexpected Dodo call {method} {path}")

    monkeypatch.setattr(dodo, "_request", fake_request)
    return calls


def _set(db, email, **fields):
    with Session(db) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        for k, v in fields.items():
            setattr(user, k, v)
        session.add(user)
        session.commit()


# --- checkout ---

def test_checkout_requires_login(client):
    assert client.post("/billing/checkout", json={"product_key": "credits_50"}).status_code == 401


def test_checkout_is_unavailable_until_billing_is_configured(client, db, products):
    headers = register_and_login(client, "b1@test.dev")
    link_dodo_product(db, "credits_50", "pdt_fifty")

    resp = client.post("/billing/checkout", json={"product_key": "credits_50"}, headers=headers)

    assert resp.status_code == 503


def test_checkout_rejects_unknown_inactive_or_unlinked_products(client, db, products, billing_on, admin_headers):
    headers = register_and_login(client, "b2@test.dev")
    link_dodo_product(db, "credits_50", "pdt_fifty")
    post = lambda key: client.post("/billing/checkout", json={"product_key": key}, headers=headers).status_code  # noqa: E731

    assert post("nope") == 404
    assert post("credits_10") == 404  # exists, but no Dodo product linked
    pack_id = next(p["id"] for p in client.get("/admin/products", headers=admin_headers).json() if p["key"] == "credits_50")
    client.put(f"/admin/products/{pack_id}", json={"active": False}, headers=admin_headers)
    assert post("credits_50") == 404


def test_checkout_creates_a_dodo_session_carrying_the_user_and_product(client, db, products, billing_on, dodo_calls):
    headers = register_and_login(client, "b3@test.dev")
    link_dodo_product(db, "credits_50", "pdt_credits")
    user_id = get_user(db, "b3@test.dev").id

    resp = client.post("/billing/checkout", json={"product_key": "credits_50"}, headers=headers)

    assert resp.status_code == 200
    assert resp.json() == {"checkout_url": "https://checkout.dodo.test/cks_1"}
    (method, path, body), = dodo_calls
    assert (method, path) == ("POST", "/checkouts")
    assert body["product_cart"] == [{"product_id": "pdt_credits", "quantity": 1}]
    assert body["customer"] == {"email": "b3@test.dev"}
    assert body["metadata"] == {"user_id": str(user_id), "product_key": "credits_50"}
    assert body["return_url"] == "https://app.test/dashboard/billing?checkout=success"
    assert body["cancel_url"] == "https://app.test/dashboard/billing?checkout=cancelled"


def test_checkout_reuses_an_existing_dodo_customer(client, db, products, billing_on, dodo_calls):
    headers = register_and_login(client, "b4@test.dev")
    link_dodo_product(db, "credits_50", "pdt_credits")
    _set(db, "b4@test.dev", dodo_customer_id="cus_123")

    client.post("/billing/checkout", json={"product_key": "credits_50"}, headers=headers)

    assert dodo_calls[0][2]["customer"] == {"customer_id": "cus_123"}


def test_every_pack_can_be_bought_again(client, db, products, billing_on, dodo_calls):
    """Credits are consumable - buying the same pack twice is the normal case,
    not a duplicate to block (what the old subscription check did)."""
    headers = register_and_login(client, "b5@test.dev")
    link_dodo_product(db, "credits_50", "pdt_credits")

    first = client.post("/billing/checkout", json={"product_key": "credits_50"}, headers=headers)
    second = client.post("/billing/checkout", json={"product_key": "credits_50"}, headers=headers)

    assert (first.status_code, second.status_code) == (200, 200)
    assert len(dodo_calls) == 2


def test_a_dodo_failure_surfaces_as_502(client, db, products, billing_on, monkeypatch):
    headers = register_and_login(client, "b7@test.dev")
    link_dodo_product(db, "credits_50", "pdt_credits")

    def boom(*a, **k):
        raise dodo.DodoError("Dodo Payments error 401: bad key")

    monkeypatch.setattr(dodo, "_request", boom)

    resp = client.post("/billing/checkout", json={"product_key": "credits_50"}, headers=headers)

    assert resp.status_code == 502 and "bad key" in resp.json()["detail"]


# --- portal ---

def test_portal_needs_a_billing_account_first(client, db, products, billing_on, dodo_calls):
    headers = register_and_login(client, "p1@test.dev")

    assert client.post("/billing/portal", headers=headers).status_code == 400

    _set(db, "p1@test.dev", dodo_customer_id="cus_9")
    resp = client.post("/billing/portal", headers=headers)
    assert resp.status_code == 200 and resp.json() == {"url": "https://portal.dodo.test/abc"}
    assert dodo_calls[0] == ("POST", "/customers/cus_9/customer-portal/session", {"return_url": "https://app.test/dashboard/billing"})


def test_portal_is_unavailable_without_billing_keys(client, db):
    headers = register_and_login(client, "p2@test.dev")
    _set(db, "p2@test.dev", dodo_customer_id="cus_9")
    assert client.post("/billing/portal", headers=headers).status_code == 503


# --- summary ---

def test_billing_summary_shows_credits_packs_and_own_payments_only(client, db, products, billing_on):
    headers = register_and_login(client, "s1@test.dev")
    other = register_and_login(client, "s2@test.dev")
    mine, theirs = get_user(db, "s1@test.dev"), get_user(db, "s2@test.dev")
    _set(db, "s1@test.dev", dodo_customer_id="cus_1")
    with Session(db) as session:
        session.add(Payment(user_id=mine.id, amount_cents=500, kind=PaymentKind.credit_pack.value,
                            product_key="credits_50", credits_granted=50, provider="dodo", provider_ref="pay_a"))
        session.add(Payment(user_id=theirs.id, amount_cents=999, kind=PaymentKind.manual.value, provider="manual"))
        session.commit()

    body = client.get("/billing", headers=headers).json()

    assert body["credits_balance"] == 3 and body["credits_purchased"] == 50
    assert body["billing_enabled"] is True and body["can_manage_billing"] is True
    assert [p["amount_cents"] for p in body["payments"]] == [500]  # not the other user's 999
    assert body["payments"][0]["product_key"] == "credits_50"
    assert "provider_ref" not in body["payments"][0]
    # the same packs the landing page offers, so there is one source of truth
    assert [p["key"] for p in body["packs"]] == ["credits_10", "credits_50", "credits_200"]

    fresh = client.get("/billing", headers=other).json()
    assert fresh["can_manage_billing"] is False and fresh["credits_purchased"] == 0


# --- the Dodo HTTP layer ---

def test_dodo_requests_hit_the_right_host_with_a_bearer_key(monkeypatch):
    seen = {}

    def fake_httpx(method, url, headers=None, json=None, timeout=None):
        seen.update(method=method, url=url, headers=headers, json=json)
        return httpx.Response(200, json={"checkout_url": "https://x"}, request=httpx.Request(method, url))

    monkeypatch.setattr(dodo.httpx, "request", fake_httpx)
    monkeypatch.setattr("app.config.settings.dodo_api_key", "sk_test_1")

    monkeypatch.setattr("app.config.settings.dodo_environment", "test_mode")
    dodo.create_checkout_session(product_id="p", email="a@b.c", customer_id=None, metadata={"a": "b"}, return_url="https://r")
    assert seen["url"] == "https://test.dodopayments.com/checkouts"
    assert seen["headers"] == {"Authorization": "Bearer sk_test_1"}

    monkeypatch.setattr("app.config.settings.dodo_environment", "live_mode")
    dodo.create_checkout_session(product_id="p", email="a@b.c", customer_id=None, metadata={}, return_url="https://r")
    assert seen["url"] == "https://live.dodopayments.com/checkouts"

    monkeypatch.setattr("app.config.settings.dodo_base_url", "http://localhost:9099/")
    dodo.create_checkout_session(product_id="p", email="a@b.c", customer_id=None, metadata={}, return_url="https://r")
    assert seen["url"] == "http://localhost:9099/checkouts"  # override wins, trailing slash tolerated


def test_dodo_errors_are_wrapped(monkeypatch):
    monkeypatch.setattr("app.config.settings.dodo_api_key", "k")

    monkeypatch.setattr(dodo.httpx, "request", lambda *a, **k: httpx.Response(401, text="unauthorized", request=httpx.Request("GET", "https://x")))
    with pytest.raises(dodo.DodoError, match="401"):
        dodo.get_product("pdt_1")

    def offline(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(dodo.httpx, "request", offline)
    with pytest.raises(dodo.DodoError, match="Could not reach"):
        dodo.get_product("pdt_1")

    monkeypatch.setattr("app.config.settings.dodo_api_key", "")
    with pytest.raises(dodo.DodoError, match="not configured"):
        dodo.get_product("pdt_1")


def test_admin_can_compare_a_shown_price_with_dodos(client, db, products, billing_on, admin_headers, monkeypatch):
    pack_id = next(p["id"] for p in client.get("/admin/products", headers=admin_headers).json() if p["key"] == "credits_50")
    verify = lambda: client.post(f"/admin/products/{pack_id}/verify", headers=admin_headers).json()  # noqa: E731

    assert verify()["ok"] is False and "No Dodo product" in verify()["message"]

    link_dodo_product(db, "credits_50", "pdt_fifty")
    monkeypatch.setattr(dodo, "get_product", lambda pid: {"price": {"price": 500, "currency": "USD", "type": "one_time_price"}})
    assert verify() == {"ok": True, "message": "Matches Dodo.", "dodo_price_cents": 500, "dodo_currency": "USD"}

    monkeypatch.setattr(dodo, "get_product", lambda pid: {"price": {"price": 900, "currency": "USD"}})
    mismatch = verify()
    assert mismatch["ok"] is False and "$5.00" in mismatch["message"] and "$9.00" in mismatch["message"]

    monkeypatch.setattr(dodo, "get_product", lambda pid: {"price": {"price": 500, "currency": "EUR"}})
    assert verify()["ok"] is False and "EUR" in verify()["message"]

    def down(pid):
        raise dodo.DodoError("Dodo Payments error 500")

    monkeypatch.setattr(dodo, "get_product", down)
    assert verify()["ok"] is False
