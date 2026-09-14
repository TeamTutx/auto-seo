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
    (REQUIREMENTS.md §2.4 competitor comparison)."""
    provider = get_rank_provider()
    own_domain = normalize_domain(own_url)
    results = provider.fetch_serp(keyword, location_code, language_code, device)
    return [r for r in results if r.domain != own_domain][:limit]
