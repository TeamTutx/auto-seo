import json

from sqlmodel import Session, select

from app.models import AdminAuditLog, Payment, PlanTier
from tests.conftest import ADMIN_EMAIL, get_user, grant_credits, make_page, register_and_login


def _user_id(db, email):
    return get_user(db, email).id


# --- access control ---

def test_admin_routes_require_login(client):
    for path in ["/admin/stats", "/admin/users", "/admin/users/1", "/admin/products"]:
        assert client.get(path).status_code == 401, path


def test_a_normal_user_gets_403_on_every_admin_route(client, monkeypatch):
    monkeypatch.setattr("app.config.settings.admin_emails", "someone.else@test.dev")
    headers = register_and_login(client, "plain@test.dev")

    calls = [
        client.get("/admin/stats", headers=headers),
        client.get("/admin/users", headers=headers),
        client.get("/admin/users/1", headers=headers),
        client.post("/admin/users/1/credits", json={"delta": 5, "note": "sneaky"}, headers=headers),
        client.post("/admin/users/1/plan", json={"plan": "agency", "note": "sneaky"}, headers=headers),
        client.post("/admin/users/1/payments", json={"amount_cents": 1, "note": "sneaky"}, headers=headers),
        client.get("/admin/products", headers=headers),
        client.put("/admin/products/1", json={"price_cents": 1}, headers=headers),
    ]
    assert [c.status_code for c in calls] == [403] * len(calls)


def test_admin_flag_comes_from_the_env_allowlist_not_the_account(client, monkeypatch):
    monkeypatch.setattr("app.config.settings.admin_emails", "")
    headers = register_and_login(client, ADMIN_EMAIL)
    assert client.get("/auth/me", headers=headers).json()["is_admin"] is False
    assert client.get("/admin/stats", headers=headers).status_code == 403

    monkeypatch.setattr("app.config.settings.admin_emails", f" {ADMIN_EMAIL.upper()} , other@x.com")
    assert client.get("/auth/me", headers=headers).json()["is_admin"] is True  # case/space-insensitive
    assert client.get("/admin/stats", headers=headers).status_code == 200

    monkeypatch.setattr("app.config.settings.admin_emails", "other@x.com")  # revoked - same token
    assert client.get("/admin/stats", headers=headers).status_code == 403


# --- users list ---

def _seed_users(client, db, admin_headers):
    register_and_login(client, "alice@test.dev")
    register_and_login(client, "bob@test.dev")
    register_and_login(client, "carol@test.dev")
    client.post(
        f"/admin/users/{_user_id(db, 'bob@test.dev')}/payments",
        json={"amount_cents": 2400, "plan": "pro", "note": "UPI"}, headers=admin_headers,
    )
    client.post(
        f"/admin/users/{_user_id(db, 'carol@test.dev')}/payments",
        json={"amount_cents": 900, "credits": 50, "note": "bank"}, headers=admin_headers,
    )


def test_user_list_shows_plan_credits_and_total_paid(client, db, admin_headers):
    _seed_users(client, db, admin_headers)

    body = client.get("/admin/users", headers=admin_headers).json()

    assert body["total"] == 4
    rows = {r["email"]: r for r in body["items"]}
    assert rows["bob@test.dev"]["plan"] == "pro" and rows["bob@test.dev"]["total_paid_cents"] == 2400
    assert rows["carol@test.dev"]["credits_balance"] == 53 and rows["carol@test.dev"]["total_paid_cents"] == 900
    assert rows["alice@test.dev"]["total_paid_cents"] == 0
    assert rows[ADMIN_EMAIL]["is_admin"] is True and rows["alice@test.dev"]["is_admin"] is False


def test_user_list_search_and_filters(client, db, admin_headers):
    _seed_users(client, db, admin_headers)
    get = lambda **params: client.get("/admin/users", params=params, headers=admin_headers).json()  # noqa: E731

    assert [r["email"] for r in get(q="ALI")["items"]] == ["alice@test.dev"]  # case-insensitive
    assert {r["email"] for r in get(plan="pro")["items"]} == {"bob@test.dev"}
    assert {r["email"] for r in get(paid="true")["items"]} == {"bob@test.dev", "carol@test.dev"}
    assert {r["email"] for r in get(paid="false")["items"]} == {"alice@test.dev", ADMIN_EMAIL}
    assert get(paid="true")["total"] == 2


def test_user_list_sorting_and_pagination(client, db, admin_headers):
    _seed_users(client, db, admin_headers)
    get = lambda **params: client.get("/admin/users", params=params, headers=admin_headers).json()  # noqa: E731

    assert get(sort="total_paid", order="desc")["items"][0]["email"] == "bob@test.dev"
    assert get(sort="credits", order="desc")["items"][0]["email"] == "carol@test.dev"
    assert get(sort="email", order="asc")["items"][0]["email"] == "admin@test.dev"

    page1 = get(sort="email", order="asc", page=1, page_size=3)
    page2 = get(sort="email", order="asc", page=2, page_size=3)
    assert page1["total"] == page2["total"] == 4
    assert len(page1["items"]) == 3 and [r["email"] for r in page2["items"]] == ["carol@test.dev"]

    assert client.get("/admin/users", params={"sort": "hashed_password"}, headers=admin_headers).status_code == 422


def test_no_admin_response_ever_contains_a_password_hash(client, db, admin_headers):
    _seed_users(client, db, admin_headers)
    uid = _user_id(db, "alice@test.dev")
    hashed = get_user(db, "alice@test.dev").hashed_password

    bodies = [
        client.get("/admin/users", headers=admin_headers).text,
        client.get(f"/admin/users/{uid}", headers=admin_headers).text,
        client.get("/admin/stats", headers=admin_headers).text,
        client.post(f"/admin/users/{uid}/credits", json={"delta": 1, "note": "check"}, headers=admin_headers).text,
    ]
    for body in bodies:
        assert hashed not in body and "hashed_password" not in body


# --- user detail ---

def test_user_detail_has_sites_payments_ledger_and_audit(client, db, admin_headers):
    headers = register_and_login(client, "detail@test.dev")
    make_page(client, headers, domain="detail.example")
    uid = _user_id(db, "detail@test.dev")
    client.post(f"/admin/users/{uid}/credits", json={"delta": 10, "note": "welcome gift"}, headers=admin_headers)
    client.post(f"/admin/users/{uid}/payments", json={"amount_cents": 500, "note": "tip"}, headers=admin_headers)

    detail = client.get(f"/admin/users/{uid}", headers=admin_headers).json()

    assert detail["sites"] == [{"id": detail["sites"][0]["id"], "domain": "detail.example", "verified": False, "pages_count": 1}]
    assert detail["total_paid_cents"] == 500 and detail["payments"][0]["provider"] == "manual"
    assert [(t["delta"], t["reason"]) for t in detail["ledger"]] == [(10, "admin"), (3, "signup")]
    assert detail["ledger"][0]["actor_email"] == ADMIN_EMAIL
    assert {a["action"] for a in detail["audit"]} == {"credits_adjusted", "payment_recorded"}
    assert detail["google_connected"] is False
    assert client.get("/admin/users/99999", headers=admin_headers).status_code == 404


# --- credit adjustments ---

def test_admin_can_add_credits_and_it_is_ledgered_and_audited(client, db, admin_headers):
    register_and_login(client, "topup@test.dev")
    uid = _user_id(db, "topup@test.dev")

    resp = client.post(f"/admin/users/{uid}/credits", json={"delta": 25, "note": "beta tester"}, headers=admin_headers)

    assert resp.status_code == 200
    assert resp.json()["credits_balance"] == 28
    assert get_user(db, "topup@test.dev").credits_balance == 28
    with Session(db) as session:
        log = session.exec(select(AdminAuditLog).where(AdminAuditLog.action == "credits_adjusted")).one()
        assert log.target_user_id == uid and log.actor_id == _user_id(db, ADMIN_EMAIL)
        assert json.loads(log.payload) == {"delta": 25, "note": "beta tester"}


def test_admin_can_remove_credits_but_not_below_zero(client, db, admin_headers):
    register_and_login(client, "shrink@test.dev")
    uid = _user_id(db, "shrink@test.dev")

    ok = client.post(f"/admin/users/{uid}/credits", json={"delta": -3, "note": "abuse cleanup"}, headers=admin_headers)
    too_much = client.post(f"/admin/users/{uid}/credits", json={"delta": -1, "note": "one more"}, headers=admin_headers)

    assert ok.status_code == 200 and ok.json()["credits_balance"] == 0
    assert too_much.status_code == 400 and "can't remove" in too_much.json()["detail"]
    assert get_user(db, "shrink@test.dev").credits_balance == 0


def test_credit_adjustment_validation(client, db, admin_headers):
    register_and_login(client, "valid@test.dev")
    uid = _user_id(db, "valid@test.dev")
    post = lambda body: client.post(f"/admin/users/{uid}/credits", json=body, headers=admin_headers).status_code  # noqa: E731

    assert post({"delta": 0, "note": "nothing"}) == 422
    assert post({"delta": 10_001, "note": "too many"}) == 422
    assert post({"delta": 5, "note": ""}) == 422  # a reason is mandatory
    assert post({"delta": 5}) == 422
    assert client.post("/admin/users/99999/credits", json={"delta": 5, "note": "ghost"}, headers=admin_headers).status_code == 404


# --- plan + manual payments ---

def test_admin_can_change_a_plan_and_it_is_audited(client, db, admin_headers):
    register_and_login(client, "upgrade@test.dev")
    uid = _user_id(db, "upgrade@test.dev")

    resp = client.post(f"/admin/users/{uid}/plan", json={"plan": "agency", "note": "comped"}, headers=admin_headers)

    assert resp.status_code == 200 and resp.json()["plan"] == "agency"
    assert get_user(db, "upgrade@test.dev").plan == PlanTier.agency
    with Session(db) as session:
        log = session.exec(select(AdminAuditLog).where(AdminAuditLog.action == "plan_changed")).one()
        assert json.loads(log.payload) == {"from": "free", "to": "agency", "note": "comped"}
    assert client.post(f"/admin/users/{uid}/plan", json={"plan": "platinum", "note": "nope"}, headers=admin_headers).status_code == 422


def test_manual_payment_records_money_grants_credits_and_switches_plan(client, db, admin_headers):
    register_and_login(client, "paid@test.dev")
    uid = _user_id(db, "paid@test.dev")

    resp = client.post(
        f"/admin/users/{uid}/payments",
        json={"amount_cents": 2400, "credits": 20, "plan": "pro", "note": "UPI ref 123"},
        headers=admin_headers,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["total_paid_cents"] == 2400 and body["plan"] == "pro" and body["credits_balance"] == 23
    assert body["payments"][0]["credits_granted"] == 20 and body["payments"][0]["kind"] == "manual"
    assert body["ledger"][0]["reason"] == "admin" and body["ledger"][0]["delta"] == 20


def test_manual_payment_validation(client, db, admin_headers):
    register_and_login(client, "pv@test.dev")
    uid = _user_id(db, "pv@test.dev")
    post = lambda body: client.post(f"/admin/users/{uid}/payments", json=body, headers=admin_headers).status_code  # noqa: E731

    assert post({"amount_cents": -5, "note": "negative"}) == 422
    assert post({"amount_cents": 100, "credits": -1, "note": "neg credits"}) == 422
    assert post({"amount_cents": 100}) == 422  # note required
    assert post({"amount_cents": 100, "note": "okay"}) == 201


# --- overview ---

def test_stats_summarise_users_revenue_and_credits(client, db, products, admin_headers):
    _seed_users(client, db, admin_headers)
    uid = _user_id(db, "alice@test.dev")
    client.post(f"/admin/users/{uid}/payments", json={"amount_cents": 500, "note": "tip"}, headers=admin_headers)

    stats = client.get("/admin/stats", headers=admin_headers).json()

    assert stats["total_users"] == 4 and stats["signups_7d"] == 4 and stats["signups_30d"] == 4
    assert stats["users_by_plan"] == {"free": 3, "pro": 1, "agency": 0}
    assert stats["paying_users"] == 3
    assert stats["revenue_all_cents"] == 2400 + 900 + 500 and stats["revenue_30d_cents"] == 3800
    assert stats["estimated_mrr_cents"] == 2400  # one Pro user x the $24 catalog price
    assert stats["credits_outstanding"] == 4 * 3 + 50
    assert len(stats["recent_signups"]) == 4 and stats["recent_actions"][0]["action"] == "payment_recorded"


def test_credits_spent_counts_only_usage_over_the_last_30_days(client, db, admin_headers, monkeypatch):
    import app.services.keyword_rank_runner as runner
    from tests.test_credit_ledger import _Provider

    monkeypatch.setattr(runner, "get_rank_provider", lambda: _Provider())
    headers = register_and_login(client, "spender@test.dev")
    page_id = make_page(client, headers)
    client.post(f"/pages/{page_id}/keywords", json={"keyword": "a"}, headers=headers)
    client.post(f"/pages/{page_id}/keywords", json={"keyword": "b"}, headers=headers)
    client.post(f"/admin/users/{_user_id(db, 'spender@test.dev')}/credits", json={"delta": -1, "note": "not usage"}, headers=admin_headers)

    assert client.get("/admin/stats", headers=admin_headers).json()["credits_spent_30d"] == 2


# --- product catalog ---

def test_admin_can_list_and_edit_products(client, db, products, admin_headers):
    listed = client.get("/admin/products", headers=admin_headers).json()
    assert [p["key"] for p in listed] == ["pro", "agency", "credits_50"]

    pro = listed[0]
    resp = client.put(
        f"/admin/products/{pro['id']}",
        json={"price_cents": 1900, "name": "Pro+", "dodo_product_id": " pdt_pro_1 ", "description": "Best value"},
        headers=admin_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert (body["price_cents"], body["name"], body["dodo_product_id"]) == (1900, "Pro+", "pdt_pro_1")
    with Session(db) as session:
        log = session.exec(select(AdminAuditLog).where(AdminAuditLog.action == "product_updated")).one()
        assert json.loads(log.payload)["before"]["price_cents"] == 2400


def test_clearing_the_dodo_link_and_validation_rules(client, db, products, admin_headers):
    ids = {p["key"]: p["id"] for p in client.get("/admin/products", headers=admin_headers).json()}
    client.put(f"/admin/products/{ids['pro']}", json={"dodo_product_id": "pdt_1"}, headers=admin_headers)

    cleared = client.put(f"/admin/products/{ids['pro']}", json={"dodo_product_id": ""}, headers=admin_headers)
    assert cleared.json()["dodo_product_id"] is None

    client.put(f"/admin/products/{ids['pro']}", json={"dodo_product_id": "pdt_1"}, headers=admin_headers)
    clash = client.put(f"/admin/products/{ids['agency']}", json={"dodo_product_id": "pdt_1"}, headers=admin_headers)
    assert clash.status_code == 409  # one Dodo product can't back two catalog entries

    assert client.put(f"/admin/products/{ids['pro']}", json={"price_cents": -1}, headers=admin_headers).status_code == 422
    assert client.put(f"/admin/products/{ids['pro']}", json={"credits": 5}, headers=admin_headers).status_code == 422  # subscriptions have no credits
    assert client.put("/admin/products/9999", json={"name": "x"}, headers=admin_headers).status_code == 404


def test_admin_can_add_a_credit_pack_but_not_duplicate_keys(client, db, products, admin_headers):
    body = {"key": "credits_200", "name": "200 credits", "price_cents": 2900, "credits": 200}

    created = client.post("/admin/products", json=body, headers=admin_headers)

    assert created.status_code == 201
    assert created.json()["kind"] == "credit_pack" and created.json()["sort_order"] > 30
    assert client.post("/admin/products", json=body, headers=admin_headers).status_code == 409
    assert client.post("/admin/products", json={**body, "key": "Bad Key!"}, headers=admin_headers).status_code == 422
    assert client.post("/admin/products", json={**body, "key": "zero", "credits": 0}, headers=admin_headers).status_code == 422
