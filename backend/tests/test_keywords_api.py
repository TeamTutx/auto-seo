import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.services.keyword_rank_runner as keyword_rank_runner
from app.database import get_session
from app.main import app
from app.models import User
from app.services.rank_providers.base import RankProvider


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


def _grant_credits(db, email, amount):
    """Bypass the API to set a user's balance directly - lets a test isolate the
    keyword-limit gate from the credit gate instead of running out of the
    latter first (every check, new or recheck, spends 1 credit)."""
    with Session(db) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        user.credits_balance = amount
        session.add(user)
        session.commit()


class _FakeProvider(RankProvider):
    name = "fake"

    def __init__(self, sequence):
        self.sequence = sequence
        self.i = 0

    def fetch_rank(self, keyword, target_domain, location_code, language_code, device):
        value = self.sequence[self.i % len(self.sequence)]
        self.i += 1
        return value


@pytest.fixture
def fake_ranks(monkeypatch):
    def _install(sequence):
        provider = _FakeProvider(sequence)
        monkeypatch.setattr(keyword_rank_runner, "get_rank_provider", lambda: provider)

    return _install


def _register_and_login(client, email):
    client.post("/auth/register", json={"email": email, "password": "correct-horse-battery"})
    resp = client.post("/auth/login", data={"username": email, "password": "correct-horse-battery"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_page(client, headers):
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()
    page = client.post(f"/sites/{site['id']}/pages", json={"url": "https://example.com/"}, headers=headers).json()
    return page["id"]


def test_add_keyword_persists_rank_and_spends_a_credit(client, fake_ranks):
    fake_ranks([7])
    headers = _register_and_login(client, "kw1@test.dev")
    page_id = _make_page(client, headers)

    resp = client.post(f"/pages/{page_id}/keywords", json={"keyword": "vitamin c serum"}, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["rank_position"] == 7
    assert body["provider"] == "fake"

    me = client.get("/auth/me", headers=headers).json()
    assert me["credits_balance"] == 2  # started at 3, spent 1


def test_free_plan_keyword_limit(client, fake_ranks):
    fake_ranks([1, 2, 3, 4])
    headers = _register_and_login(client, "kw2@test.dev")
    page_id = _make_page(client, headers)

    for kw in ["a", "b", "c"]:
        assert client.post(f"/pages/{page_id}/keywords", json={"keyword": kw}, headers=headers).status_code == 201

    resp = client.post(f"/pages/{page_id}/keywords", json={"keyword": "d"}, headers=headers)
    assert resp.status_code == 402


def test_rechecking_existing_keyword_does_not_count_against_limit(client, fake_ranks, db):
    fake_ranks([5, 4, 3, 2])
    headers = _register_and_login(client, "kw3@test.dev")
    page_id = _make_page(client, headers)
    _grant_credits(db, "kw3@test.dev", 10)

    for kw in ["a", "b", "c"]:
        client.post(f"/pages/{page_id}/keywords", json={"keyword": kw}, headers=headers)

    # already at the free plan's 3-keyword cap; rechecking "a" isn't a *new*
    # keyword so it must still succeed
    resp = client.post(f"/pages/{page_id}/keywords", json={"keyword": "a"}, headers=headers)
    assert resp.status_code == 201


def test_recheck_all_requires_enough_credits_for_every_tracked_keyword(client, fake_ranks):
    fake_ranks([10])
    headers = _register_and_login(client, "kw4@test.dev")
    page_id = _make_page(client, headers)

    client.post(f"/pages/{page_id}/keywords", json={"keyword": "a"}, headers=headers)
    client.post(f"/pages/{page_id}/keywords", json={"keyword": "b"}, headers=headers)
    # credits now 1 remaining (started at 3, spent 2) - rechecking both needs 2

    resp = client.post(f"/pages/{page_id}/keywords/recheck", headers=headers)
    assert resp.status_code == 402


def test_list_and_history_return_latest_and_full_history_per_keyword(client, fake_ranks):
    fake_ranks([9, 8])
    headers = _register_and_login(client, "kw5@test.dev")
    page_id = _make_page(client, headers)

    client.post(f"/pages/{page_id}/keywords", json={"keyword": "a"}, headers=headers)
    client.post(f"/pages/{page_id}/keywords", json={"keyword": "a"}, headers=headers)

    listing = client.get(f"/pages/{page_id}/keywords", headers=headers).json()
    assert len(listing) == 1
    assert listing[0]["rank_position"] == 8

    history = client.get(f"/pages/{page_id}/keywords/history", params={"keyword": "a"}, headers=headers).json()
    assert [h["rank_position"] for h in history] == [9, 8]
