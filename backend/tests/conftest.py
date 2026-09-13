import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import get_session
from app.main import app
from app.models import User


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def get_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_session_override
    yield engine
    app.dependency_overrides.clear()


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
