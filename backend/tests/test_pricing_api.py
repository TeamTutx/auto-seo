from sqlmodel import Session, select

from app.models import ACCOUNT_LIMITS, SIGNUP_CREDITS, Product
from app.services.billing import DEFAULT_PRODUCTS, seed_default_products
from tests.conftest import link_dodo_product


def test_pricing_is_public_and_lists_the_credit_packs(client, products):
    resp = client.get("/pricing")  # no auth header

    assert resp.status_code == 200
    body = resp.json()
    assert body["signup_credits"] == SIGNUP_CREDITS
    assert body["limits"] == ACCOUNT_LIMITS  # the same for everyone; there are no tiers
    assert [p["key"] for p in body["credit_packs"]] == ["credits_10", "credits_50", "credits_200"]
    assert body["credit_packs"][1] == {
        "key": "credits_50", "name": "50 credits", "price_cents": 500, "credits": 50,
        "description": None, "badge": "Best value", "price_per_credit_cents": 10.0, "purchasable": False,
    }
    assert "max-age" in resp.headers["cache-control"]


def test_the_owner_can_add_a_pack_and_it_appears_on_the_public_page(client, products, admin_headers):
    created = client.post(
        "/admin/products",
        json={"key": "credits_1000", "name": "1000 credits", "price_cents": 5000, "credits": 1000,
              "description": "Bulk", "badge": "Bulk"},
        headers=admin_headers,
    )
    assert created.status_code == 201

    packs = client.get("/pricing").json()["credit_packs"]
    assert [p["key"] for p in packs] == ["credits_10", "credits_50", "credits_200", "credits_1000"]
    assert packs[-1]["price_per_credit_cents"] == 5.0  # $50 / 1000 credits


def test_the_owner_can_reorder_packs_and_visitors_see_the_new_order(client, products, admin_headers):
    ids = {p["key"]: p["id"] for p in client.get("/admin/products", headers=admin_headers).json()}

    resp = client.post(
        "/admin/products/reorder",
        json={"ids": [ids["credits_200"], ids["credits_10"], ids["credits_50"]]},
        headers=admin_headers,
    )

    assert resp.status_code == 200
    assert [p["key"] for p in client.get("/pricing").json()["credit_packs"]] == [
        "credits_200", "credits_10", "credits_50",
    ]


def test_reorder_refuses_a_partial_or_unknown_list(client, products, admin_headers):
    ids = [p["id"] for p in client.get("/admin/products", headers=admin_headers).json()]

    partial = client.post("/admin/products/reorder", json={"ids": ids[:2]}, headers=admin_headers)
    assert partial.status_code == 422

    unknown = client.post("/admin/products/reorder", json={"ids": ids + [9999]}, headers=admin_headers)
    assert unknown.status_code == 404

    # the original order survived both refusals
    assert [p["key"] for p in client.get("/pricing").json()["credit_packs"]] == [
        "credits_10", "credits_50", "credits_200",
    ]


def test_editing_a_price_in_admin_changes_what_visitors_see(client, products, admin_headers):
    pack_id = next(
        p["id"] for p in client.get("/admin/products", headers=admin_headers).json() if p["key"] == "credits_50"
    )

    client.put(f"/admin/products/{pack_id}", json={"price_cents": 400, "name": "50 credits (sale)"}, headers=admin_headers)

    pack = next(p for p in client.get("/pricing").json()["credit_packs"] if p["key"] == "credits_50")
    assert (pack["name"], pack["price_cents"], pack["price_per_credit_cents"]) == ("50 credits (sale)", 400, 8.0)


def test_inactive_products_are_hidden_from_the_public_page(client, products, admin_headers):
    listed = {p["key"]: p["id"] for p in client.get("/admin/products", headers=admin_headers).json()}

    client.put(f"/admin/products/{listed['credits_10']}", json={"active": False}, headers=admin_headers)

    assert [p["key"] for p in client.get("/pricing").json()["credit_packs"]] == ["credits_50", "credits_200"]
    # still in the admin catalog, just not for sale
    assert len(client.get("/admin/products", headers=admin_headers).json()) == 3


def test_a_pack_nobody_bought_can_be_deleted(client, products, admin_headers):
    pack_id = next(
        p["id"] for p in client.get("/admin/products", headers=admin_headers).json() if p["key"] == "credits_10"
    )

    assert client.delete(f"/admin/products/{pack_id}", headers=admin_headers).status_code == 204
    assert [p["key"] for p in client.get("/pricing").json()["credit_packs"]] == ["credits_50", "credits_200"]


def test_purchasable_needs_billing_configured_and_a_linked_dodo_product(client, db, products, monkeypatch):
    packs = lambda: {p["key"]: p["purchasable"] for p in client.get("/pricing").json()["credit_packs"]}  # noqa: E731

    link_dodo_product(db, "credits_50", "pdt_fifty")
    assert packs()["credits_50"] is False  # billing keys not set yet
    assert client.get("/pricing").json()["billing_enabled"] is False

    monkeypatch.setattr("app.config.settings.dodo_api_key", "k")
    monkeypatch.setattr("app.config.settings.dodo_webhook_key", "w")
    assert packs() == {"credits_10": False, "credits_50": True, "credits_200": False}
    assert client.get("/pricing").json()["billing_enabled"] is True


def test_the_default_catalog_is_seeded_into_an_empty_table_exactly_once(client, db):
    with Session(db) as session:
        assert seed_default_products(session) == len(DEFAULT_PRODUCTS) == 3
        assert seed_default_products(session) == 0  # idempotent
        assert {p.key for p in session.exec(select(Product)).all()} == {"credits_10", "credits_50", "credits_200"}

    # local dev, which builds its database with create_all(), is never left with
    # an empty pricing page
    assert len(client.get("/pricing").json()["credit_packs"]) == 3


def test_seeding_never_overwrites_an_admins_edits_or_refills_a_curated_catalog(client, db, products, admin_headers):
    pack_id = next(
        p["id"] for p in client.get("/admin/products", headers=admin_headers).json() if p["key"] == "credits_50"
    )
    client.put(f"/admin/products/{pack_id}", json={"price_cents": 1900}, headers=admin_headers)

    with Session(db) as session:
        assert seed_default_products(session) == 0  # the table isn't empty
        assert session.get(Product, pack_id).price_cents == 1900

    # even a catalog the owner has pruned down to a single product stays as they left it
    with Session(db) as session:
        for p in session.exec(select(Product).where(Product.key != "credits_50")).all():
            session.delete(p)
        session.commit()
        assert seed_default_products(session) == 0
        assert [p.key for p in session.exec(select(Product)).all()] == ["credits_50"]
