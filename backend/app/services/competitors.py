from typing import List

from app.services.rank_providers import get_rank_provider
from app.services.rank_providers.base import SerpResult, normalize_domain


def get_competitors(
    keyword: str,
    own_url: str,
    location_code: int,
    language_code: str,
    device: str,
    limit: int = 5,
) -> List[SerpResult]:
    """Top organic results for keyword, excluding own_url's own domain
    (REQUIREMENTS.md §2.4 competitor comparison).

    Unlike a rank check (which needs to scan deep to tell "ranks on page 8"
    from "not found"), this only ever returns the top `limit` results - so it
    asks the provider for a much shallower scan (a small buffer over `limit`
    in case one of the top results turns out to be our own domain), instead
    of the default 100-result scrape. That's most of why competitor/keyword-
    opportunity lookups were slow enough to time out."""
    provider = get_rank_provider()
    own_domain = normalize_domain(own_url)
    results = provider.fetch_serp(keyword, location_code, language_code, device, num_results=limit + 10)
    return [r for r in results if r.domain != own_domain][:limit]
