from app.config import settings

from .base import RankProvider, RankProviderError
from .dataforseo import DataForSEOProvider
from .serpapi import SerpApiProvider

_PROVIDERS = {
    "dataforseo": DataForSEOProvider,
    "serpapi": SerpApiProvider,
}


def get_rank_provider() -> RankProvider:
    key = settings.rank_provider.lower()
    try:
        provider_cls = _PROVIDERS[key]
    except KeyError:
        raise RankProviderError(
            f"Unknown RANK_PROVIDER '{settings.rank_provider}'. Choose one of: {', '.join(_PROVIDERS)}."
        )
    return provider_cls()


__all__ = ["RankProvider", "RankProviderError", "get_rank_provider"]
