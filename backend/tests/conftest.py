import base64
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import get_session
from app.config import settings
from app.main import app
from app.models import Product, User


# Set TEST_DATABASE_URL (e.g. postgresql://...) to run the whole suite against a
# real Postgres instead of in-memory SQLite. SQLite doesn't enforce enum labels,
# unique-constraint edge cases or row locking the way production does (see the
# enum gotcha in CLAUDE.md), so run it that way before shipping schema changes.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def db():
    if TEST_DATABASE_URL:
        engine = create_engine(TEST_DATABASE_URL)
        SQLModel.metadata.drop_all(engine)
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def get_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_session_override
    yield engine
    app.dependency_overrides.clear()
    if TEST_DATABASE_URL:
        engine.dispose()


@pytest.fixture
def client(db):
    return TestClient(app)


def register_and_login(client, email):
    client.post("/auth/register", json={"email": email, "password": "correct-horse-battery"})
    resp = client.post("/auth/login", data={"username": email, "password": "correct-horse-battery"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def make_page(client, headers, domain="example.com", url=None):
    site = client.post("/sites", json={"domain": domain}, headers=headers).json()
    page = client.post(
        f"/sites/{site['id']}/pages", json={"url": url or f"https://{domain}/"}, headers=headers
    ).json()
    return page["id"]


def grant_credits(db, email, amount):
    """Bypass the API to set a user's balance directly - lets a test isolate one
    gate (e.g. a plan limit) from the credit gate instead of running out of
    the latter first."""
    with Session(db) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        user.credits_balance = amount
        session.add(user)
        session.commit()


# --- billing / admin helpers ---

ADMIN_EMAIL = "admin@test.dev"
WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"k" * 24).decode()


@pytest.fixture
def admin_headers(client, monkeypatch):
    """Auth headers for a registered admin (ADMIN_EMAILS is patched for the test)."""
    monkeypatch.setattr(settings, "admin_emails", ADMIN_EMAIL)
    return register_and_login(client, ADMIN_EMAIL)


@pytest.fixture
def products(db):
    """The default catalog the 0008 migration seeds (create_all doesn't run it)."""
    with Session(db) as session:
        session.add_all([
            Product(key="pro", name="Pro", kind="subscription", price_cents=2400, interval="month", plan="pro", sort_order=10),
            Product(key="agency", name="Agency", kind="subscription", price_cents=8900, interval="month", plan="agency", sort_order=20),
            Product(key="credits_50", name="50 credits", kind="credit_pack", price_cents=900, credits=50, sort_order=30),
        ])
        session.commit()


@pytest.fixture
def billing_on(monkeypatch):
    monkeypatch.setattr(settings, "dodo_api_key", "test_api_key")
    monkeypatch.setattr(settings, "dodo_webhook_key", WEBHOOK_SECRET)
    monkeypatch.setattr(settings, "dodo_environment", "test_mode")
    monkeypatch.setattr(settings, "frontend_url", "https://app.test")


def link_dodo_product(db, key, dodo_product_id):
    with Session(db) as session:
        product = session.exec(select(Product).where(Product.key == key)).first()
        product.dodo_product_id = dodo_product_id
        session.add(product)
        session.commit()


def get_user(db, email):
    with Session(db) as session:
        return session.exec(select(User).where(User.email == email)).first()
