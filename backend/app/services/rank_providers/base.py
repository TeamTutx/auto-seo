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


@dataclass
class AIOverview:
    """Google's AI answer box, when the SERP had one. `sources` are the pages it
    cited, already normalize_domain()'d, which is how we tell whether a site is
    being used as a source rather than merely ranking below the box."""
    present: bool
    sources: List[str]
    text: str = ""


@dataclass
class SerpSnapshot:
    """Everything one search told us. Fetching organic results and the AI
    Overview together matters: they come back in a single vendor response, so
    splitting them into two calls would double what a visibility check costs."""
    results: List[SerpResult]
    ai_overview: Optional[AIOverview] = None


class RankProvider(ABC):
    name: str

    @abstractmethod
    def fetch_serp(
        self,
        keyword: str,
        location_code: int,
        language_code: str,
        device: str,
        num_results: int = 100,
    ) -> List[SerpResult]:
        """Return the organic results this provider found for keyword, ordered
        by position. This is the one real call to the vendor API - fetch_rank
        and competitor lookups both just filter/search this list, so there's
        exactly one place that parses a vendor's response shape.

        num_results controls how deep the vendor scans (default 100, enough to
        tell "ranks on page 8" from "not found"). Callers that only need the
        top few results (competitor comparison) should pass a much smaller
        value - asking for 100 when 15 would do is most of why those lookups
        were slow enough to time out."""

    def fetch_snapshot(
        self,
        keyword: str,
        location_code: int,
        language_code: str,
        device: str,
        num_results: int = 100,
    ) -> "SerpSnapshot":
        """Organic results plus any SERP features this vendor exposes. The
        default is organic only, so a vendor that can't report AI Overviews
        simply reports nothing rather than needing to fake it."""
        return SerpSnapshot(
            results=self.fetch_serp(keyword, location_code, language_code, device, num_results),
            ai_overview=None,
        )

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
