import app.routers.google_integration as google_integration_router
import app.services.ga as ga_service
import app.services.gsc as gsc_service
from app.security import create_access_token
from tests.conftest import make_page, register_and_login


def _connect_google(client, monkeypatch, email):
    state = create_access_token(subject=email)
    monkeypatch.setattr(
        google_integration_router,
        "exchange_code",
        lambda code: {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600},
    )
    client.get(f"/integrations/google/callback?code=abc&state={state}", follow_redirects=False)


def test_gsc_queries_without_google_connected_returns_400(client):
    headers = register_and_login(client, "gd1@test.dev")
    page_id = make_page(client, headers)

    resp = client.get(f"/pages/{page_id}/gsc/queries", headers=headers)
    assert resp.status_code == 400
    assert "Connect Google" in resp.json()["detail"]


def test_gsc_queries_without_a_linked_property_returns_400(client, monkeypatch):
    headers = register_and_login(client, "gd2@test.dev")
    _connect_google(client, monkeypatch, "gd2@test.dev")
    page_id = make_page(client, headers)

    resp = client.get(f"/pages/{page_id}/gsc/queries", headers=headers)
    assert resp.status_code == 400
    assert "Search Console property" in resp.json()["detail"]


def test_gsc_queries_returns_rows_once_configured(client, monkeypatch):
    headers = register_and_login(client, "gd3@test.dev")
    _connect_google(client, monkeypatch, "gd3@test.dev")

    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()
    client.patch(f"/sites/{site['id']}", json={"gsc_property": "sc-domain:example.com"}, headers=headers)
    page = client.post(
        f"/sites/{site['id']}/pages", json={"url": "https://example.com/serum"}, headers=headers
    ).json()

    monkeypatch.setattr(
        gsc_service,
        "get_page_search_analytics",
        lambda token, prop, url, days=28: [
            {"query": "vitamin c serum", "clicks": 5, "impressions": 100, "ctr": 5.0, "position": 9.2}
        ],
    )

    resp = client.get(f"/pages/{page['id']}/gsc/queries", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == [
        {"query": "vitamin c serum", "clicks": 5, "impressions": 100, "ctr": 5.0, "position": 9.2}
    ]


def test_gsc_queries_provider_error_returns_502(client, monkeypatch):
    from app.services.gsc import GSCError

    headers = register_and_login(client, "gd4@test.dev")
    _connect_google(client, monkeypatch, "gd4@test.dev")
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()
    client.patch(f"/sites/{site['id']}", json={"gsc_property": "sc-domain:example.com"}, headers=headers)
    page = client.post(
        f"/sites/{site['id']}/pages", json={"url": "https://example.com/serum"}, headers=headers
    ).json()

    def _boom(token, prop, url, days=28):
        raise GSCError("quota exceeded")

    monkeypatch.setattr(gsc_service, "get_page_search_analytics", _boom)

    resp = client.get(f"/pages/{page['id']}/gsc/queries", headers=headers)
    assert resp.status_code == 502


def test_gsc_index_status_returns_result_once_configured(client, monkeypatch):
    headers = register_and_login(client, "gd5@test.dev")
    _connect_google(client, monkeypatch, "gd5@test.dev")
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()
    client.patch(f"/sites/{site['id']}", json={"gsc_property": "sc-domain:example.com"}, headers=headers)
    page = client.post(
        f"/sites/{site['id']}/pages", json={"url": "https://example.com/serum"}, headers=headers
    ).json()

    monkeypatch.setattr(
        gsc_service,
        "inspect_url",
        lambda token, prop, url: {
            "indexed": False,
            "verdict": "NEUTRAL",
            "coverage_state": "Discovered - currently not indexed",
            "last_crawl_time": None,
        },
    )

    resp = client.get(f"/pages/{page['id']}/gsc/index-status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["indexed"] is False


def test_ga_metrics_without_a_linked_property_returns_400(client, monkeypatch):
    headers = register_and_login(client, "gd6@test.dev")
    _connect_google(client, monkeypatch, "gd6@test.dev")
    page_id = make_page(client, headers)

    resp = client.get(f"/pages/{page_id}/ga/metrics", headers=headers)
    assert resp.status_code == 400
    assert "Analytics property" in resp.json()["detail"]


def test_ga_metrics_returns_data_once_configured(client, monkeypatch):
    headers = register_and_login(client, "gd7@test.dev")
    _connect_google(client, monkeypatch, "gd7@test.dev")
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()
    client.patch(f"/sites/{site['id']}", json={"ga_property_id": "12345"}, headers=headers)
    page = client.post(
        f"/sites/{site['id']}/pages", json={"url": "https://example.com/serum"}, headers=headers
    ).json()

    monkeypatch.setattr(
        ga_service,
        "get_page_metrics",
        lambda token, prop, path, days=28: {
            "sessions": 42, "pageviews": 88, "bounce_rate": 33.3, "avg_session_duration": 51.2
        },
    )

    resp = client.get(f"/pages/{page['id']}/ga/metrics", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["sessions"] == 42


def test_gsc_queries_requires_page_ownership(client, monkeypatch):
    headers1 = register_and_login(client, "gd8a@test.dev")
    headers2 = register_and_login(client, "gd8b@test.dev")
    _connect_google(client, monkeypatch, "gd8b@test.dev")
    page_id = make_page(client, headers1)

    resp = client.get(f"/pages/{page_id}/gsc/queries", headers=headers2)
    assert resp.status_code == 404
