"""DataForSEO SERP integration (REQUIREMENTS.md §2.4, §7 provider decision).

Split into a pure response parser (`extract_rank`, easy to unit test with
fixture JSON) and the actual API call (`fetch_rank`, needs real credentials
and network access, so it's untested here - see backend/README.md).
"""
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.config import settings

DATAFORSEO_URL = "https://api.dataforseo.com/v3/serp/google/organic/live/regular"
SEARCH_DEPTH = 100  # how many organic results to scan for the target domain


class RankProviderError(Exception):
    pass


def _normalize_domain(value: str) -> str:
    netloc = urlparse(value if "//" in value else f"//{value}").netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def extract_rank(response_json: dict, target_domain: str) -> Optional[int]:
    """Find target_domain's rank_absolute in a DataForSEO SERP response, or None if absent."""
    target = _normalize_domain(target_domain)
    try:
        items = response_json["tasks"][0]["result"][0]["items"] or []
    except (KeyError, IndexError, TypeError):
        return None

    for item in items:
        if item.get("type") != "organic":
            continue
        item_domain = item.get("domain") or _normalize_domain(item.get("url", ""))
        if _normalize_domain(item_domain) == target:
            return item.get("rank_absolute")
    return None


def fetch_rank(
    keyword: str,
    target_domain: str,
    location_code: int = 2840,
    language_code: str = "en",
    device: str = "desktop",
) -> Optional[int]:
    if not settings.dataforseo_login or not settings.dataforseo_password:
        raise RankProviderError("DataForSEO credentials are not configured (DATAFORSEO_LOGIN/PASSWORD).")

    payload = [{
        "keyword": keyword,
        "location_code": location_code,
        "language_code": language_code,
        "device": device,
        "depth": SEARCH_DEPTH,
    }]

    try:
        response = httpx.post(
            DATAFORSEO_URL,
            json=payload,
            auth=(settings.dataforseo_login, settings.dataforseo_password),
            timeout=30.0,
        )
    except httpx.TransportError as exc:
        raise RankProviderError(f"DataForSEO request failed: {exc}") from exc

    # DataForSEO returns a JSON body with status_code/status_message on 4xx/5xx
    # responses too (e.g. unverified account, insufficient balance) - that detail
    # is far more useful than the bare HTTP status, so parse before checking it.
    try:
        data = response.json()
    except ValueError:
        response.raise_for_status()
        raise RankProviderError(f"DataForSEO returned a non-JSON {response.status_code} response.")

    if data.get("status_code") != 20000:
        raise RankProviderError(f"DataForSEO error: {data.get('status_message', 'unknown error')}")

    return extract_rank(data, target_domain)
