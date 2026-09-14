import httpx
import pytest

from app.services.ga import GAError, get_page_metrics, list_properties


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
    assert captured["json"]["dimensionFilter"]["filter"]["stringFilter"]["value"] == "/serum"
    assert metrics == {"sessions": 120, "pageviews": 200, "bounce_rate": 45.0, "avg_session_duration": 38.2}


def test_get_page_metrics_with_no_rows_returns_zeros(monkeypatch):
    def fake_request(method, url, headers, timeout, json=None):
        return httpx.Response(200, json={"rows": []}, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", fake_request)
    metrics = get_page_metrics("token-1", "12345", "/never-visited")
    assert metrics == {"sessions": 0, "pageviews": 0, "bounce_rate": 0.0, "avg_session_duration": 0.0}


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
