"""Google Analytics Data API (GA4). Real traffic per page - sessions,
pageviews, bounce rate, engagement - a different signal from anything SEO
audits or rank checks give: a page can score well and rank well yet still
not convert visitors, and this is the only place that would show up.
"""
from datetime import date, timedelta
from typing import List

import httpx

ACCOUNT_SUMMARIES_URL = "https://analyticsadmin.googleapis.com/v1beta/accountSummaries"
RUN_REPORT_URL = "https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"


class GAError(Exception):
    pass


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _request(method: str, url: str, access_token: str, **kwargs) -> dict:
    try:
        response = httpx.request(method, url, headers=_headers(access_token), timeout=15.0, **kwargs)
    except httpx.TransportError as exc:
        raise GAError(f"Could not reach Analytics: {exc}") from exc

    try:
        data = response.json()
    except ValueError:
        response.raise_for_status()
        raise GAError(f"Analytics returned a non-JSON {response.status_code} response.")

    if "error" in data:
        raise GAError(data["error"].get("message", "unknown Analytics error"))
    return data


def list_properties(access_token: str) -> List[dict]:
    """Every GA4 property this Google account has at least read access to -
    shown to the user so they can pick which one belongs to which Signal
    site (Settings page)."""
    data = _request("GET", ACCOUNT_SUMMARIES_URL, access_token)
    properties = []
    for account in data.get("accountSummaries", []):
        for prop in account.get("propertySummaries", []):
            properties.append({
                "property_id": prop["property"].split("/")[-1],
                "display_name": prop.get("displayName", ""),
            })
    return properties


def get_page_metrics(access_token: str, property_id: str, page_path: str, days: int = 28) -> dict:
    end = date.today()
    start = end - timedelta(days=days)
    payload = {
        "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
        "dimensions": [{"name": "pagePath"}],
        "metrics": [
            {"name": "sessions"},
            {"name": "screenPageViews"},
            {"name": "bounceRate"},
            {"name": "averageSessionDuration"},
        ],
        "dimensionFilter": {
            "filter": {"fieldName": "pagePath", "stringFilter": {"matchType": "EXACT", "value": page_path}}
        },
    }
    url = RUN_REPORT_URL.format(property_id=property_id)
    data = _request("POST", url, access_token, json=payload)

    rows = data.get("rows", [])
    if not rows:
        return {"sessions": 0, "pageviews": 0, "bounce_rate": 0.0, "avg_session_duration": 0.0}

    values = rows[0]["metricValues"]
    return {
        "sessions": int(values[0]["value"]),
        "pageviews": int(values[1]["value"]),
        "bounce_rate": round(float(values[2]["value"]) * 100, 1),
        "avg_session_duration": round(float(values[3]["value"]), 1),
    }
