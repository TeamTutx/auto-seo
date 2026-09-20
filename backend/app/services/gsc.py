"""Google Search Console API. A different, complementary data source to the
SerpApi/DataForSEO rank checks: those tell you where YOUR page ranks for a
keyword YOU specify, this tells you what people are ACTUALLY searching that
leads to clicks on your page - including queries you never thought to
track - plus whether Google has even indexed the page at all, which is the
real answer to "why does this page have zero rank" for a brand new page.
"""
from datetime import date, timedelta
from typing import List, Optional
from urllib.parse import quote, urlparse, urlunparse

import httpx

SITES_URL = "https://searchconsole.googleapis.com/webmasters/v3/sites"
SEARCH_ANALYTICS_URL = "https://searchconsole.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"
INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"

MAX_QUERY_ROWS = 25
# Keyword discovery wants a wide net, unlike the per-page table above which is
# capped at what a person will actually read.
MAX_SITE_QUERY_ROWS = 200


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


def slash_variants(page_url: str) -> List[str]:
    """The URL as given, then the same URL with its trailing slash toggled.

    Search Console's page filter is an exact string match against the canonical
    URL *Google* chose, and sites disagree about trailing slashes: WordPress
    serves /about/, Next.js serves /about, and Google records whichever one the
    site actually canonicalises to. One character of disagreement returns zero
    rows - which looks exactly like "this page gets no search traffic" and is
    impossible to tell apart from the real thing. Trying both costs one extra
    request, and only in the case that would otherwise report nothing."""
    parsed = urlparse(page_url)
    path = parsed.path or "/"
    if path == "/":
        other = ""  # https://site.com/ vs https://site.com
    elif path.endswith("/"):
        other = path.rstrip("/")
    else:
        other = path + "/"
    return [page_url, urlunparse(parsed._replace(path=other))]


def _page_filtered_rows(access_token: str, property_url: str, page_url: str, payload: dict) -> List[dict]:
    """Run a page-filtered Search Analytics query, retrying the other
    trailing-slash form if the first returns nothing. See slash_variants."""
    url = SEARCH_ANALYTICS_URL.format(site=quote(property_url, safe=""))
    for candidate in slash_variants(page_url):
        body = dict(payload)
        body["dimensionFilterGroups"] = [
            {"filters": [{"dimension": "page", "operator": "equals", "expression": candidate}]}
        ]
        rows = _request("POST", url, access_token, json=body).get("rows", [])
        if rows:
            return rows
    return []


def get_page_search_analytics(access_token: str, property_url: str, page_url: str, days: int = 28) -> List[dict]:
    end = date.today()
    start = end - timedelta(days=days)
    rows = _page_filtered_rows(access_token, property_url, page_url, {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["query"],
        "rowLimit": MAX_QUERY_ROWS,
    })
    return [
        {
            "query": row["keys"][0],
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": round(row.get("ctr", 0) * 100, 2),
            "position": round(row.get("position", 0), 1),
        }
        for row in rows
    ]


def get_site_search_analytics(access_token: str, property_url: str, days: int = 28, limit: int = 100) -> List[dict]:
    """The site's top search queries, across every page. This is the only
    keyword source Signal has that is real measured data rather than a guess -
    these are terms Google already shows the site for, so they are the best
    place to look for something worth targeting properly."""
    end = date.today()
    start = end - timedelta(days=days)
    payload = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["query"],
        "rowLimit": min(limit, MAX_SITE_QUERY_ROWS),
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


def get_page_daily_metrics(access_token: str, property_url: str, page_url: str, days: int = 28) -> List[dict]:
    """One row per day for a single page: clicks, impressions and average
    position. This is the page's actual search performance over time - the only
    trend line Signal can draw from measured data rather than inference.

    Search Console lags roughly two days, so the most recent dates are usually
    missing rather than zero. Days with no impressions simply aren't returned;
    the caller fills the gaps so the chart has a continuous x-axis."""
    end = date.today()
    start = end - timedelta(days=days)
    rows = _page_filtered_rows(access_token, property_url, page_url, {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["date"],
        "rowLimit": days + 1,
    })
    return [
        {
            "date": row["keys"][0],
            "clicks": int(row.get("clicks", 0)),
            "impressions": int(row.get("impressions", 0)),
            "position": round(row.get("position", 0), 1),
        }
        for row in rows
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
