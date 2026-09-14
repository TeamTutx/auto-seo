"""Common contract every rank-data vendor integration implements.

Add a new vendor by subclassing RankProvider and registering it in
__init__.py's _PROVIDERS map - nothing else in the app imports a vendor
module directly, so swapping the active one is a one-line env var change
(RANK_PROVIDER) with no code touched outside this package.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse


class RankProviderError(Exception):
    pass


@dataclass
class SerpResult:
    position: int
    title: str
    domain: str  # already normalize_domain()'d
    url: str


class RankProvider(ABC):
    name: str

    @abstractmethod
    def fetch_serp(
        self,
        keyword: str,
        location_code: int,
        language_code: str,
        device: str,
    ) -> List[SerpResult]:
        """Return the organic results this provider found for keyword, ordered
        by position. This is the one real call to the vendor API - fetch_rank
        and competitor lookups both just filter/search this list, so there's
        exactly one place that parses a vendor's response shape."""

    def fetch_rank(
        self,
        keyword: str,
        target_domain: str,
        location_code: int,
        language_code: str,
        device: str,
    ) -> Optional[int]:
        """Return target_domain's absolute organic search position for keyword,
        or None if it doesn't appear in the results this provider checked."""
        target = normalize_domain(target_domain)
        for result in self.fetch_serp(keyword, location_code, language_code, device):
            if result.domain == target:
                return result.position
        return None


def normalize_domain(value: str) -> str:
    netloc = urlparse(value if "//" in value else f"//{value}").netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc
