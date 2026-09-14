import httpx
import pytest

from app.services.gsc import GSCError, get_page_search_analytics, inspect_url, list_properties


def test_list_properties_parses_site_entries(monkeypatch):
    def fake_request(method, url, headers, timeout):
        assert method == "GET"
        return httpx.Response(
            200,
            json={"siteEntry": [{"siteUrl": "sc-domain:example.com"}, {"siteUrl": "https://other.com/"}]},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    result = list_properties("token-1")
    assert result == ["sc-domain:example.com", "https://other.com/"]


def test_get_page_search_analytics_parses_rows_and_filters_by_page(monkeypatch):
    captured = {}

    def fake_request(method, url, headers, timeout, json=None):
        captured["method"] = method
        captured["json"] = json
        return httpx.Response(
            200,
            json={
                "rows": [
                    {"keys": ["vitamin c serum"], "clicks": 12, "impressions": 300, "ctr": 0.04, "position": 8.3},
                ]
            },
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    rows = get_page_search_analytics("token-1", "sc-domain:example.com", "https://example.com/serum")

    assert captured["method"] == "POST"
    assert captured["json"]["dimensionFilterGroups"][0]["filters"][0]["expression"] == "https://example.com/serum"
    assert rows == [
        {"query": "vitamin c serum", "clicks": 12, "impressions": 300, "ctr": 4.0, "position": 8.3}
    ]


def test_inspect_url_reports_indexed_when_verdict_is_pass(monkeypatch):
    def fake_request(method, url, headers, timeout, json=None):
        return httpx.Response(
            200,
            json={
                "inspectionResult": {
                    "indexStatusResult": {
                        "verdict": "PASS",
                        "coverageState": "Submitted and indexed",
                        "lastCrawlTime": "2026-09-01T00:00:00Z",
                    }
                }
            },
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    result = inspect_url("token-1", "sc-domain:example.com", "https://example.com/serum")
    assert result == {
        "indexed": True,
        "verdict": "PASS",
        "coverage_state": "Submitted and indexed",
        "last_crawl_time": "2026-09-01T00:00:00Z",
    }


def test_inspect_url_reports_not_indexed_for_other_verdicts(monkeypatch):
    def fake_request(method, url, headers, timeout, json=None):
        return httpx.Response(
            200,
            json={"inspectionResult": {"indexStatusResult": {"verdict": "NEUTRAL", "coverageState": "Discovered"}}},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    result = inspect_url("token-1", "sc-domain:example.com", "https://example.com/new-page")
    assert result["indexed"] is False
    assert result["verdict"] == "NEUTRAL"


def test_error_response_raises_gsc_error(monkeypatch):
    def fake_request(method, url, headers, timeout, json=None):
        return httpx.Response(
            403, json={"error": {"message": "User does not have sufficient permission."}}, request=httpx.Request(method, url)
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    with pytest.raises(GSCError, match="sufficient permission"):
        list_properties("token-1")


def test_transport_error_is_wrapped(monkeypatch):
    def fake_request(method, url, headers, timeout, json=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "request", fake_request)
    with pytest.raises(GSCError, match="Could not reach Search Console"):
        list_properties("token-1")
