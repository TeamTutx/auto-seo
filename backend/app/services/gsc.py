"""Google Search Console API. A different, complementary data source to the
SerpApi/DataForSEO rank checks: those tell you where YOUR page ranks for a
keyword YOU specify, this tells you what people are ACTUALLY searching that
leads to clicks on your page - including queries you never thought to
track - plus whether Google has even indexed the page at all, which is the
real answer to "why does this page have zero rank" for a brand new page.
"""
from datetime import date, timedelta
from typing import List, Optional
from urllib.parse import quote

import httpx

SITES_URL = "https://searchconsole.googleapis.com/webmasters/v3/sites"
SEARCH_ANALYTICS_URL = "https://searchconsole.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"
INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"

MAX_QUERY_ROWS = 25


class GSCError(Exception):
    pass


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _request(method: str, url: str, access_token: str, **kwargs) -> dict:
    try:
        response = httpx.request(method, url, headers=_headers(access_token), timeout=15.0, **kwargs)
    except httpx.TransportError as exc:
        raise GSCError(f"Could not reach Search Console: {exc}") from exc

    try:
        data = response.json()
    except ValueError:
        response.raise_for_status()
        raise GSCError(f"Search Console returned a non-JSON {response.status_code} response.")

    if "error" in data:
        raise GSCError(data["error"].get("message", "unknown Search Console error"))
    return data


def list_properties(access_token: str) -> List[str]:
    """Every Search Console property (domain or URL-prefix) this Google
    account has at least read access to - shown to the user so they can pick
    which one belongs to which Signal site (Settings page)."""
    data = _request("GET", SITES_URL, access_token)
    return [entry["siteUrl"] for entry in data.get("siteEntry", [])]


def get_page_search_analytics(access_token: str, property_url: str, page_url: str, days: int = 28) -> List[dict]:
    end = date.today()
    start = end - timedelta(days=days)
    payload = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["query"],
        "dimensionFilterGroups": [
            {"filters": [{"dimension": "page", "operator": "equals", "expression": page_url}]}
        ],
        "rowLimit": MAX_QUERY_ROWS,
    }
    url = SEARCH_ANALYTICS_URL.format(site=quote(property_url, safe=""))
    data = _request("POST", url, access_token, json=payload)
    return [
        {
            "query": row["keys"][0],
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": round(row.get("ctr", 0) * 100, 2),
            "position": round(row.get("position", 0), 1),
        }
        for row in data.get("rows", [])
    ]


def inspect_url(access_token: str, property_url: str, page_url: str) -> dict:
    payload = {"inspectionUrl": page_url, "siteUrl": property_url}
    data = _request("POST", INSPECT_URL, access_token, json=payload)
    result = data.get("inspectionResult", {}).get("indexStatusResult", {})
    verdict = result.get("verdict", "UNKNOWN")
    return {
        "indexed": verdict == "PASS",
        "verdict": verdict,
        "coverage_state": result.get("coverageState", ""),
        "last_crawl_time": result.get("lastCrawlTime"),
    }
