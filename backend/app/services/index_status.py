"""Is this page actually in Google's index?

A page that isn't indexed cannot rank, however good its audit score is, which
makes this the first thing worth knowing about a newly crawled site.

Two ways to find out, and the difference matters:

- **Search Console URL Inspection** is Google telling you directly. Free,
  authoritative, and it explains *why* a page isn't indexed. It needs the owner
  to have connected Google and to be an owner of the property - plenty of people
  only have delegated access, which the API refuses.
- **A `site:` search** is inference: ask Google for that exact URL and see if it
  comes back. Costs a credit, is less precise (Google is inconsistent about
  `site:` for deep pages), but works for anyone.

So: try Search Console, fall back to the paid lookup, and always record which
one answered so the UI can be honest about how sure it is.
"""
import logging
from datetime import datetime
from typing import Optional

from app.models import Page
from app.services import gsc
from app.services.gsc import GSCError
from app.services.rank_providers import get_rank_provider
from app.services.rank_providers.base import RankProviderError, normalize_domain

logger = logging.getLogger("signal.index")

INDEXED = "indexed"
NOT_INDEXED = "not_indexed"
UNKNOWN = "unknown"

# Google's own wording, passed through so the owner sees the real reason
# ("Crawled - currently not indexed" is a very different problem from
# "Excluded by 'noindex' tag").
_VERDICT_LABEL = {
    "PASS": "Indexed",
    "PARTIAL": "Indexed with warnings",
    "FAIL": "Not indexed",
    "NEUTRAL": "Not indexed",
}


def check_via_gsc(access_token: str, property_url: str, page_url: str) -> dict:
    result = gsc.inspect_url(access_token, property_url, page_url)
    status = INDEXED if result["indexed"] else NOT_INDEXED
    detail = result.get("coverage_state") or _VERDICT_LABEL.get(result.get("verdict", ""), "")
    return {"status": status, "detail": detail, "source": "gsc"}


def check_via_serp(page_url: str) -> dict:
    """`site:<url>` returns the page itself when Google has it. Matching on the
    normalised URL rather than just the domain matters - `site:` on a deep path
    will happily return other pages from the same site."""
    provider = get_rank_provider()
    target = page_url.rstrip("/")
    results = provider.fetch_serp(
        keyword=f"site:{target}", location_code=2840, language_code="en",
        device="desktop", num_results=10,
    )
    for result in results:
        if result.url.rstrip("/") == target:
            return {"status": INDEXED, "detail": "Found by site: search", "source": "serp"}
    # Google returning *something* for the domain but not this URL is weak
    # evidence of absence, which is the best a site: search can offer.
    if results and normalize_domain(target) == results[0].domain:
        return {"status": NOT_INDEXED, "detail": "Not returned by a site: search", "source": "serp"}
    return {"status": UNKNOWN, "detail": "site: search returned nothing", "source": "serp"}


def apply_to_page(page: Page, result: dict) -> None:
    page.index_status = result["status"]
    page.index_detail = (result.get("detail") or "")[:300] or None
    page.index_source = result["source"]
    page.index_checked_at = datetime.utcnow()


def check_page(page_url: str, access_token: Optional[str], property_url: Optional[str]) -> Optional[dict]:
    """Best available answer, or None if only a paid lookup could help and the
    caller hasn't agreed to spend a credit. Search Console failing for one URL
    (not an owner, quota exhausted) shouldn't abort a whole crawl, so errors
    here are logged and turned into "no answer"."""
    if access_token and property_url:
        try:
            return check_via_gsc(access_token, property_url, page_url)
        except GSCError as exc:
            logger.info("URL Inspection unavailable for %s: %s", page_url, exc)
    return None


def check_page_paid(page_url: str) -> dict:
    try:
        return check_via_serp(page_url)
    except RankProviderError as exc:
        logger.info("site: lookup failed for %s: %s", page_url, exc)
        return {"status": UNKNOWN, "detail": str(exc)[:200], "source": "serp"}
