from typing import List

import httpx

from app.config import settings

from .base import RankProvider, RankProviderError, SerpResult, normalize_domain


class DataForSEOProvider(RankProvider):
    name = "dataforseo"

    URL = "https://api.dataforseo.com/v3/serp/google/organic/live/regular"
    # A short connect timeout (DataForSEO is either reachable or it isn't) but a
    # generous read timeout - a deep-depth scrape can genuinely take a while.
    TIMEOUT = httpx.Timeout(10.0, read=45.0)

    def fetch_serp(
        self,
        keyword: str,
        location_code: int = 2356,
        language_code: str = "en",
        device: str = "desktop",
        num_results: int = 100,
    ) -> List[SerpResult]:
        if not settings.dataforseo_login or not settings.dataforseo_password:
            raise RankProviderError("DataForSEO credentials are not configured (DATAFORSEO_LOGIN/PASSWORD).")

        payload = [{
            "keyword": keyword,
            "location_code": location_code,
            "language_code": language_code,
            "device": device,
            "depth": num_results,
        }]

        response = self._post_with_retry(payload)

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

        return self.parse_serp(data)

    def _post_with_retry(self, payload: list) -> httpx.Response:
        """One retry on a read timeout - a fresh connection often succeeds
        where waiting longer on the same one wouldn't."""
        for attempt in range(2):
            try:
                return httpx.post(
                    self.URL,
                    json=payload,
                    auth=(settings.dataforseo_login, settings.dataforseo_password),
                    timeout=self.TIMEOUT,
                )
            except httpx.TimeoutException:
                if attempt == 1:
                    raise RankProviderError(
                        "DataForSEO request timed out twice in a row. It may be under heavy load - try again shortly."
                    )
            except httpx.TransportError as exc:
                raise RankProviderError(f"DataForSEO request failed: {exc}") from exc
        raise AssertionError("unreachable")  # loop always returns or raises

    @staticmethod
    def parse_serp(response_json: dict) -> List[SerpResult]:
        try:
            items = response_json["tasks"][0]["result"][0]["items"] or []
        except (KeyError, IndexError, TypeError):
            return []

        results = []
        for item in items:
            if item.get("type") != "organic":
                continue
            raw_domain = item.get("domain") or item.get("url", "")
            position = item.get("rank_absolute")
            if position is None:
                continue
            results.append(SerpResult(
                position=position,
                title=item.get("title", ""),
                domain=normalize_domain(raw_domain),
                url=item.get("url", ""),
            ))
        return results
