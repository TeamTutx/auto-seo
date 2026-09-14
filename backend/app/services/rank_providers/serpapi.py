from typing import Optional

import httpx

from app.config import settings

from .base import RankProvider, RankProviderError, normalize_domain

# SerpApi targets a market with a 2-letter country code ("gl"), not DataForSEO's
# numeric location_code - this maps the common ones so KeywordRank rows stay
# provider-agnostic. Extend as needed; unmapped codes fall back to "us".
_LOCATION_CODE_TO_COUNTRY = {
    2840: "us",  # United States
    2826: "gb",  # United Kingdom
    2124: "ca",  # Canada
    2036: "au",  # Australia
    2356: "in",  # India
}


class SerpApiProvider(RankProvider):
    name = "serpapi"

    URL = "https://serpapi.com/search"
    NUM_RESULTS = 100  # how many organic results to scan for the target domain

    def fetch_rank(
        self,
        keyword: str,
        target_domain: str,
        location_code: int = 2356,
        language_code: str = "en",
        device: str = "desktop",
    ) -> Optional[int]:
        if not settings.serpapi_key:
            raise RankProviderError("SerpApi credentials are not configured (SERPAPI_KEY).")

        params = {
            "engine": "google",
            "q": keyword,
            "api_key": settings.serpapi_key,
            "gl": _LOCATION_CODE_TO_COUNTRY.get(location_code, "us"),
            "hl": language_code,
            "device": device,
            "num": self.NUM_RESULTS,
        }

        try:
            response = httpx.get(self.URL, params=params, timeout=30.0)
        except httpx.TransportError as exc:
            raise RankProviderError(f"SerpApi request failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            raise RankProviderError(f"SerpApi returned a non-JSON {response.status_code} response.")

        if "error" in data:
            raise RankProviderError(f"SerpApi error: {data['error']}")

        return self.extract_rank(data, target_domain)

    @staticmethod
    def extract_rank(response_json: dict, target_domain: str) -> Optional[int]:
        target = normalize_domain(target_domain)
        for item in response_json.get("organic_results", []):
            link = item.get("link", "")
            if normalize_domain(link) == target:
                return item.get("position")
        return None
