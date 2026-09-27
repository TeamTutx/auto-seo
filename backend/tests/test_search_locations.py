"""Tracking the same phrase in more than one country.

The bug these exist for: a keyword used to be identified by its name alone, so
adding "coffee beans" for the United States after India replaced it in the list,
stopped the Indian one being re-checked, and drew both countries as one line on
the history chart. The numbers looked real and were not.
"""
import pytest
from sqlmodel import Session, select

from app.models import KeywordRank, SearchLocation, Site
from app.services import keyword_rank_runner
from app.services.opportunities import get_site_opportunities
from tests.conftest import ADMIN_EMAIL, admin_headers, grant_credits, make_page, register_and_login  # noqa: F401

EMAIL = "markets@test.dev"
INDIA, US, UK = 2356, 2840, 2826


@pytest.fixture
def headers(client):
    return register_and_login(client, EMAIL)


@pytest.fixture
def page_id(client, headers, db):
    grant_credits(db, EMAIL, 60)
    return make_page(client, headers, url="https://example.com/beans")


@pytest.fixture
def locations(db):
    """The five the frontend used to hardcode, as migration 0017 seeds them."""
    with Session(db) as session:
        session.add_all([
            SearchLocation(code=INDIA, label="India", sort_order=10),
            SearchLocation(code=US, label="United States", sort_order=20),
            SearchLocation(code=UK, label="United Kingdom", sort_order=30, active=False),
        ])
        session.commit()


@pytest.fixture
def ranks(monkeypatch):
    """Rank by country, so a test can tell the two measurements apart."""
    by_location = {INDIA: 4, US: 38}

    class _ByCountry:
        name = "test"

        @staticmethod
        def fetch_rank(keyword, url, location_code, language_code, device):
            return by_location.get(location_code, 50)

    monkeypatch.setattr(keyword_rank_runner, "get_rank_provider", lambda: _ByCountry())
    return by_location


def _track(client, headers, page_id, keyword, location, device="desktop"):
    return client.post(
        f"/pages/{page_id}/keywords",
        json={"keyword": keyword, "location_code": location, "device": device},
        headers=headers,
    )


# --- the same phrase in two countries ---


def test_the_same_keyword_in_two_countries_is_two_tracked_searches(client, headers, page_id, ranks):
    _track(client, headers, page_id, "coffee beans", INDIA)
    _track(client, headers, page_id, "coffee beans", US)

    tracked = client.get(f"/pages/{page_id}/keywords", headers=headers).json()

    assert len(tracked) == 2, "keyed by name alone, the second replaced the first"
    assert {(t["keyword"], t["location_code"], t["rank_position"]) for t in tracked} == {
        ("coffee beans", INDIA, 4),
        ("coffee beans", US, 38),
    }


def test_desktop_and_mobile_are_also_separate(client, headers, page_id, ranks):
    """Same collision, same fix - device is part of what makes a search."""
    _track(client, headers, page_id, "coffee beans", INDIA, device="desktop")
    _track(client, headers, page_id, "coffee beans", INDIA, device="mobile")

    tracked = client.get(f"/pages/{page_id}/keywords", headers=headers).json()

    assert sorted(t["device"] for t in tracked) == ["desktop", "mobile"]


def test_history_does_not_mix_countries(client, headers, page_id, ranks):
    """The chart drew India's #4 and the United States' #38 as one line, so a
    second country read as a rank collapse."""
    _track(client, headers, page_id, "coffee beans", INDIA)
    _track(client, headers, page_id, "coffee beans", US)

    indian = client.get(
        f"/pages/{page_id}/keywords/history",
        params={"keyword": "coffee beans", "location_code": INDIA, "device": "desktop"},
        headers=headers,
    ).json()

    assert [r["rank_position"] for r in indian] == [4]
    assert {r["location_code"] for r in indian} == {INDIA}


def test_rechecking_covers_every_country_not_just_the_newest(client, headers, page_id, ranks, db):
    """The older country used to stop being checked entirely, silently."""
    _track(client, headers, page_id, "coffee beans", INDIA)
    _track(client, headers, page_id, "coffee beans", US)

    rechecked = client.post(f"/pages/{page_id}/keywords/recheck", headers=headers).json()

    assert sorted(r["location_code"] for r in rechecked) == [INDIA, US]


def test_deleting_one_country_leaves_the_other(client, headers, page_id, ranks):
    _track(client, headers, page_id, "coffee beans", INDIA)
    _track(client, headers, page_id, "coffee beans", US)

    client.delete(
        f"/pages/{page_id}/keywords",
        params={"keyword": "coffee beans", "location_code": INDIA, "device": "desktop"},
        headers=headers,
    )

    tracked = client.get(f"/pages/{page_id}/keywords", headers=headers).json()
    assert [t["location_code"] for t in tracked] == [US]


def test_deleting_without_a_country_still_removes_the_lot(client, headers, page_id, ranks):
    """What the keyword-only route always meant, kept so an older client works."""
    _track(client, headers, page_id, "coffee beans", INDIA)
    _track(client, headers, page_id, "coffee beans", US)

    client.delete(f"/pages/{page_id}/keywords", params={"keyword": "coffee beans"}, headers=headers)

    assert client.get(f"/pages/{page_id}/keywords", headers=headers).json() == []


def test_a_second_country_does_not_invent_a_rank_drop(client, headers, page_id, ranks, db):
    """Opportunities grouped by keyword too, so India #4 followed by the United
    States #38 raised a keyword_rank_drop for a fall that never happened."""
    _track(client, headers, page_id, "coffee beans", INDIA)
    _track(client, headers, page_id, "coffee beans", US)

    with Session(db) as session:
        site_id = session.exec(select(Site)).first().id
        drops = [o for o in get_site_opportunities(session, site_id) if o.type.value == "keyword_rank_drop"]

    assert drops == []


# --- the list itself ---


def test_the_keyword_form_is_offered_the_active_countries(client, headers, locations):
    offered = client.get("/locations", headers=headers).json()

    assert [loc["label"] for loc in offered] == ["India", "United States"]
    assert all(loc["active"] for loc in offered), "a retired market is not selectable for a new search"


def test_the_owner_can_add_a_country_without_a_deploy(client, admin_headers, locations):
    created = client.post(
        "/admin/locations", json={"code": 2276, "label": "Germany", "sort_order": 25}, headers=admin_headers
    )

    assert created.status_code == 201
    labels = [loc["label"] for loc in client.get("/locations", headers=admin_headers).json()]
    assert "Germany" in labels


def test_adding_a_country_twice_points_at_the_retired_one(client, admin_headers, locations):
    """Recreating it would orphan every reading already pointing at the old row."""
    resp = client.post(
        "/admin/locations", json={"code": UK, "label": "United Kingdom"}, headers=admin_headers
    )

    assert resp.status_code == 409
    assert "retired" in resp.json()["detail"]


def test_a_country_is_retired_not_deleted(client, admin_headers, locations, db):
    with Session(db) as session:
        row = session.exec(select(SearchLocation).where(SearchLocation.code == US)).first()
        location_id = row.id

    client.put(f"/admin/locations/{location_id}", json={"active": False}, headers=admin_headers)

    assert "United States" not in [l["label"] for l in client.get("/locations", headers=admin_headers).json()]
    with Session(db) as session:
        assert session.exec(select(SearchLocation).where(SearchLocation.code == US)).first() is not None


def test_only_the_owner_can_change_the_list(client, headers, locations):
    assert client.post("/admin/locations", json={"code": 2276, "label": "Germany"}, headers=headers).status_code == 403


# --- a site's market ---


def test_a_site_can_be_measured_in_its_own_country(client, headers, page_id, locations, db):
    with Session(db) as session:
        site_id = session.exec(select(Site)).first().id

    resp = client.patch(f"/sites/{site_id}", json={"default_location_code": US}, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["default_location_code"] == US


def test_a_site_cannot_be_pointed_at_a_country_signal_does_not_offer(client, headers, page_id, locations, db):
    with Session(db) as session:
        site_id = session.exec(select(Site)).first().id

    resp = client.patch(f"/sites/{site_id}", json={"default_location_code": 9999}, headers=headers)

    assert resp.status_code == 422
    assert "not one of the countries" in resp.json()["detail"]
