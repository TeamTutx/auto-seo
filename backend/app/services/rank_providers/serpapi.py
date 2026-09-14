from typing import List

import httpx

from app.config import settings

from .base import RankProvider, RankProviderError, SerpResult, normalize_domain

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
    # A short connect timeout (SerpApi is either reachable or it isn't) but a
    # generous read timeout - a num=100 scrape can genuinely take a while.
    TIMEOUT = httpx.Timeout(10.0, read=45.0)

    def fetch_serp(
        self,
        keyword: str,
        location_code: int = 2356,
        language_code: str = "en",
        device: str = "desktop",
        num_results: int = 100,
    ) -> List[SerpResult]:
        if not settings.serpapi_key:
            raise RankProviderError("SerpApi credentials are not configured (SERPAPI_KEY).")

        params = {
            "engine": "google",
            "q": keyword,
            "api_key": settings.serpapi_key,
            "gl": _LOCATION_CODE_TO_COUNTRY.get(location_code, "us"),
            "hl": language_code,
            "device": device,
            "num": num_results,
        }

        response = self._get_with_retry(params)

        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            raise RankProviderError(f"SerpApi returned a non-JSON {response.status_code} response.")

        if "error" in data:
            raise RankProviderError(f"SerpApi error: {data['error']}")

        return self.parse_serp(data)

    def _get_with_retry(self, params: dict) -> httpx.Response:
        """One retry on a read timeout - SerpApi occasionally takes longer
        than usual on a single attempt; a fresh connection often succeeds
        where waiting longer on the same one wouldn't."""
        for attempt in range(2):
            try:
                return httpx.get(self.URL, params=params, timeout=self.TIMEOUT)
            except httpx.TimeoutException:
                if attempt == 1:
                    raise RankProviderError(
                        "SerpApi request timed out twice in a row. It may be under heavy load - try again shortly."
                    )
            except httpx.TransportError as exc:
                raise RankProviderError(f"SerpApi request failed: {exc}") from exc
        raise AssertionError("unreachable")  # loop always returns or raises

    @staticmethod
    def parse_serp(response_json: dict) -> List[SerpResult]:
        results = []
        for item in response_json.get("organic_results", []):
            position = item.get("position")
            link = item.get("link", "")
            if position is None or not link:
                continue
            results.append(SerpResult(
                position=position,
                title=item.get("title", ""),
                domain=normalize_domain(link),
                url=link,
            ))
        return results
