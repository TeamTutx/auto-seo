from typing import List, Optional

import httpx

from app.config import settings

from .base import AIOverview, RankProvider, RankProviderError, SerpResult, SerpSnapshot, normalize_domain

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
        return self.parse_serp(self._search(keyword, location_code, language_code, device, num_results))

    def fetch_snapshot(
        self,
        keyword: str,
        location_code: int = 2356,
        language_code: str = "en",
        device: str = "desktop",
        num_results: int = 100,
    ) -> SerpSnapshot:
        """One search, both answers: the organic ranking and whether Google's AI
        Overview cited this site. Worth keeping in a single call - it is one
        billed SerpApi search either way."""
        data = self._search(keyword, location_code, language_code, device, num_results)
        return SerpSnapshot(results=self.parse_serp(data), ai_overview=self._ai_overview(data))

    def fetch_related_searches(self, keyword: str, location_code: int = 2356) -> List[str]:
        """Google's "related searches" strip. Only the top 10 results are asked
        for - the related block is at the bottom of page one either way, and a
        num=100 scrape costs the same money but takes far longer."""
        data = self._search(keyword, location_code, "en", "desktop", num_results=10)
        terms = []
        for entry in data.get("related_searches") or []:
            term = entry.get("query") if isinstance(entry, dict) else entry
            if isinstance(term, str) and term.strip():
                terms.append(term.strip())
        return terms

    def _ai_overview(self, data: dict) -> Optional[AIOverview]:
        """AI Overviews render asynchronously, so SerpApi sometimes returns only
        a `page_token` standing in for the block. Following that token costs a
        second search, which we pay: reporting "no AI Overview" when there was
        one would quietly understate exactly what this feature exists to show."""
        block = data.get("ai_overview")
        if not block:
            return None
        if block.get("page_token") and not block.get("text_blocks"):
            block = self._fetch_ai_overview_page(block["page_token"]) or block
        if block.get("error"):
            return None

        sources, texts = [], []
        for reference in block.get("references") or []:
            link = reference.get("link")
            if link:
                sources.append(normalize_domain(link))
        for text_block in block.get("text_blocks") or []:
            if text_block.get("snippet"):
                texts.append(text_block["snippet"])
            for item in text_block.get("list") or []:
                if item.get("snippet"):
                    texts.append(item["snippet"])
        if not sources and not texts:
            return None
        return AIOverview(present=True, sources=sources, text=" ".join(texts)[:2000])

    def _fetch_ai_overview_page(self, page_token: str) -> Optional[dict]:
        params = {"engine": "google_ai_overview", "page_token": page_token, "api_key": settings.serpapi_key}
        try:
            data = self._get_with_retry(params).json()
        except (RankProviderError, ValueError):
            return None
        return data.get("ai_overview")

    def _search(self, keyword: str, location_code: int, language_code: str, device: str, num_results: int) -> dict:
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
        return data

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
