import httpx
import pytest

from app.services.ga import GAError, get_page_metrics, list_properties, path_variants


def test_list_properties_parses_account_summaries(monkeypatch):
    def fake_request(method, url, headers, timeout):
        return httpx.Response(
            200,
            json={
                "accountSummaries": [
                    {
                        "propertySummaries": [
                            {"property": "properties/12345", "displayName": "My Site"},
                            {"property": "properties/67890", "displayName": "Another Site"},
                        ]
                    }
                ]
            },
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    result = list_properties("token-1")
    assert result == [
        {"property_id": "12345", "display_name": "My Site"},
        {"property_id": "67890", "display_name": "Another Site"},
    ]


def test_get_page_metrics_parses_metric_values(monkeypatch):
    captured = {}

    def fake_request(method, url, headers, timeout, json=None):
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200,
            json={
                "rows": [
                    {"metricValues": [{"value": "120"}, {"value": "200"}, {"value": "0.45"}, {"value": "38.2"}]}
                ]
            },
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    metrics = get_page_metrics("token-1", "12345", "/serum")

    assert "12345" in captured["url"]
    assert captured["json"]["dimensionFilter"]["filter"]["inListFilter"]["values"] == ["/serum", "/serum/"]
    assert metrics == {
        "sessions": 120, "pageviews": 200, "bounce_rate": 45.0, "avg_session_duration": 38.2, "has_data": True,
    }


def test_get_page_metrics_with_no_rows_returns_zeros(monkeypatch):
    def fake_request(method, url, headers, timeout, json=None):
        return httpx.Response(200, json={"rows": []}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", fake_request)
    metrics = get_page_metrics("token-1", "12345", "/never-visited")
    assert metrics == {
        "sessions": 0, "pageviews": 0, "bounce_rate": 0.0, "avg_session_duration": 0.0, "has_data": False,
    }


def test_path_variants_cover_both_slash_forms():
    assert path_variants("/pricing") == ["/pricing", "/pricing/"]
    assert path_variants("/pricing/") == ["/pricing/", "/pricing"]
    # https://example.com and https://example.com/ are the same page, and GA4
    # only ever records it as "/".
    assert path_variants("/") == ["/"]
    assert path_variants("") == ["/"]


def test_get_page_metrics_adds_up_both_slash_forms(monkeypatch):
    def fake_request(method, url, headers, timeout, json=None):
        return httpx.Response(
            200,
            json={
                "rows": [
                    {"metricValues": [{"value": "30"}, {"value": "40"}, {"value": "0.5"}, {"value": "20"}]},
                    {"metricValues": [{"value": "10"}, {"value": "15"}, {"value": "0.1"}, {"value": "60"}]},
                ]
            },
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    metrics = get_page_metrics("token-1", "12345", "/pricing")
    # rates are per-session averages, so they weight by sessions: 30 and 10
    assert metrics == {
        "sessions": 40, "pageviews": 55, "bounce_rate": 40.0, "avg_session_duration": 30.0, "has_data": True,
    }


def test_error_response_raises_ga_error(monkeypatch):
    def fake_request(method, url, headers, timeout, json=None):
        return httpx.Response(
            400, json={"error": {"message": "Invalid property ID."}}, request=httpx.Request(method, url)
        )

    monkeypatch.setattr(httpx, "request", fake_request)
    with pytest.raises(GAError, match="Invalid property ID"):
        get_page_metrics("token-1", "bad-id", "/serum")


def test_transport_error_is_wrapped(monkeypatch):
    def fake_request(method, url, headers, timeout, json=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "request", fake_request)
    with pytest.raises(GAError, match="Could not reach Analytics"):
        list_properties("token-1")
