from sqlmodel import Session, select

from app.models import Product
from app.services.billing import DEFAULT_PRODUCTS, seed_default_products
from tests.conftest import link_dodo_product


def test_pricing_is_public_and_lists_free_pro_agency_and_packs(client, products):
    resp = client.get("/pricing")  # no auth header

    assert resp.status_code == 200
    body = resp.json()
    assert [p["key"] for p in body["plans"]] == ["free", "pro", "agency"]
    free, pro, agency = body["plans"]
    assert (free["price_cents"], free["interval"], free["limits"]["max_sites"]) == (0, None, 1)
    assert (pro["name"], pro["price_cents"], pro["interval"], pro["product_key"]) == ("Pro", 2400, "month", "pro")
    assert pro["limits"] == {"max_sites": 5, "max_pages_per_site": 50, "max_keywords_per_page": 50}
    assert agency["limits"]["max_sites"] is None  # unlimited
    assert body["credit_packs"] == [{
        "key": "credits_50", "name": "50 credits", "price_cents": 900, "credits": 50,
        "description": None, "purchasable": False,
    }]
    assert "max-age" in resp.headers["cache-control"]


def test_editing_a_price_in_admin_changes_what_visitors_see(client, products, admin_headers):
    pro_id = next(p["id"] for p in client.get("/admin/products", headers=admin_headers).json() if p["key"] == "pro")

    client.put(f"/admin/products/{pro_id}", json={"price_cents": 1900, "name": "Pro+"}, headers=admin_headers)

    pro = client.get("/pricing").json()["plans"][1]
    assert (pro["name"], pro["price_cents"]) == ("Pro+", 1900)


def test_inactive_products_are_hidden_from_the_public_page(client, products, admin_headers):
    listed = {p["key"]: p["id"] for p in client.get("/admin/products", headers=admin_headers).json()}

    client.put(f"/admin/products/{listed['agency']}", json={"active": False}, headers=admin_headers)
    client.put(f"/admin/products/{listed['credits_50']}", json={"active": False}, headers=admin_headers)

    body = client.get("/pricing").json()
    assert [p["key"] for p in body["plans"]] == ["free", "pro"]
    assert body["credit_packs"] == []


def test_purchasable_needs_billing_configured_and_a_linked_dodo_product(client, db, products, monkeypatch):
    plans = lambda: {p["key"]: p["purchasable"] for p in client.get("/pricing").json()["plans"]}  # noqa: E731

    link_dodo_product(db, "pro", "pdt_pro")
    assert plans()["pro"] is False  # billing keys not set yet
    assert client.get("/pricing").json()["billing_enabled"] is False

    monkeypatch.setattr("app.config.settings.dodo_api_key", "k")
    monkeypatch.setattr("app.config.settings.dodo_webhook_key", "w")
    assert plans() == {"free": False, "pro": True, "agency": False}  # agency has no Dodo product yet
    assert client.get("/pricing").json()["billing_enabled"] is True


def test_the_default_catalog_is_seeded_into_an_empty_table_exactly_once(client, db):
    with Session(db) as session:
        assert seed_default_products(session) == len(DEFAULT_PRODUCTS) == 3
        assert seed_default_products(session) == 0  # idempotent
        assert {p.key for p in session.exec(select(Product)).all()} == {"pro", "agency", "credits_50"}

    body = client.get("/pricing").json()
    assert [p["key"] for p in body["plans"]] == ["free", "pro", "agency"]  # local dev is never missing its paid plans


def test_seeding_never_overwrites_an_admins_edits_or_refills_a_curated_catalog(client, db, products, admin_headers):
    pro_id = next(p["id"] for p in client.get("/admin/products", headers=admin_headers).json() if p["key"] == "pro")
    client.put(f"/admin/products/{pro_id}", json={"price_cents": 1900}, headers=admin_headers)

    with Session(db) as session:
        assert seed_default_products(session) == 0  # the table isn't empty
        assert session.get(Product, pro_id).price_cents == 1900

    # even a catalog the owner has pruned down to a single product stays as they left it
    with Session(db) as session:
        for p in session.exec(select(Product).where(Product.key != "pro")).all():
            session.delete(p)
        session.commit()
        assert seed_default_products(session) == 0
        assert [p.key for p in session.exec(select(Product)).all()] == ["pro"]
