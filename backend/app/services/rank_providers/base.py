"""Common contract every rank-data vendor integration implements.

Add a new vendor by subclassing RankProvider and registering it in
__init__.py's _PROVIDERS map - nothing else in the app imports a vendor
module directly, so swapping the active one is a one-line env var change
(RANK_PROVIDER) with no code touched outside this package.
"""
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import urlparse


class RankProviderError(Exception):
    pass


class RankProvider(ABC):
    name: str

    @abstractmethod
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


def normalize_domain(value: str) -> str:
    netloc = urlparse(value if "//" in value else f"//{value}").netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc
