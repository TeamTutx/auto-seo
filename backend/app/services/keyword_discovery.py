"""Suggest keywords a site could target, from three sources of very different
quality. The UI shows which source each idea came from, because the difference
is the whole point:

- **Search Console** - terms Google *already* shows this site for, with real
  impressions, clicks and average position. Measured, not guessed. Free.
  The richest vein here is queries with impressions but a poor position: the
  site is already relevant and nearly ranking.
- **The page's own content** - an LLM reads the page and proposes terms it
  should plausibly rank for. Costs a credit. No volume data.
- **Google's related searches** - what Google itself suggests alongside a
  query. Costs a credit. Also no volume data.

Signal has no search-volume database, so none of this pretends to be a traffic
estimate. Saying "we don't know the volume" is better than inventing one; if
real volumes are ever wanted, DataForSEO's Labs API is the place they'd come
from (its credentials slot already exists in config).
"""
import json
import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from app.services.ai_providers import AIProviderError, get_ai_provider
from app.services.rank_providers import get_rank_provider
from app.services.rank_providers.base import RankProviderError

logger = logging.getLogger("signal.keywords")

# A query the site already ranks worse than this for is an opportunity; better
# than this and it is already working and needs no "idea".
NEARLY_RANKING_FROM = 4.0

SYSTEM_PROMPT = (
    "You are an SEO strategist. Given a web page's content, propose search "
    "keywords the page could realistically rank for. Prefer specific, "
    "intent-bearing phrases over single broad words. Never invent search volume "
    "or difficulty numbers."
)


@dataclass
class Idea:
    keyword: str
    source: str
    rationale: Optional[str] = None
    impressions: Optional[int] = None
    clicks: Optional[int] = None
    position: Optional[float] = None


def normalise(keyword: str) -> str:
    return re.sub(r"\s+", " ", keyword or "").strip().lower()


def from_search_console(rows: List[dict]) -> List[Idea]:
    """Real queries, ordered so the near-misses come first - a term sitting at
    position 12 with 400 impressions is worth far more attention than one
    already at position 2."""
    ideas = []
    for row in rows:
        keyword = normalise(row.get("query", ""))
        if not keyword:
            continue
        position = row.get("position")
        ideas.append(Idea(
            keyword=keyword,
            source="gsc",
            rationale=None,
            impressions=row.get("impressions"),
            clicks=row.get("clicks"),
            position=position,
        ))

    def priority(idea: Idea):
        nearly = idea.position is not None and idea.position >= NEARLY_RANKING_FROM
        return (not nearly, -(idea.impressions or 0))

    return sorted(ideas, key=priority)


def from_page_content(text: str, domain: str, limit: int = 12) -> List[Idea]:
    """Ask the model what this page is about and what it could rank for."""
    snippet = text[:6000]
    user_prompt = (
        f"Website: {domain}\n\n"
        f"Page content:\n{snippet}\n\n"
        f"Propose up to {limit} search keywords this page could target. "
        'Reply with JSON only: {"keywords": [{"keyword": "...", "why": "one short reason"}]}'
    )
    try:
        raw = get_ai_provider().complete(SYSTEM_PROMPT, user_prompt, max_tokens=700)
    except AIProviderError as exc:
        logger.info("AI keyword ideas failed for %s: %s", domain, exc)
        return []
    return _parse_ai_keywords(raw, limit)


def _parse_ai_keywords(raw: str, limit: int) -> List[Idea]:
    """Models wrap JSON in prose or fences often enough that finding the object
    is more reliable than insisting the whole reply parses."""
    match = re.search(r"\{.*\}", raw or "", flags=re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return []

    ideas = []
    for entry in (data.get("keywords") or [])[:limit]:
        if isinstance(entry, str):
            keyword, why = entry, None
        elif isinstance(entry, dict):
            keyword, why = entry.get("keyword", ""), entry.get("why")
        else:
            continue
        keyword = normalise(keyword)
        if keyword:
            ideas.append(Idea(keyword=keyword, source="ai", rationale=(why or None)))
    return ideas


def from_related_searches(seed: str, location_code: int = 2356, limit: int = 10) -> List[Idea]:
    """Google's own "people also search for" terms around a seed keyword."""
    provider = get_rank_provider()
    fetch_related = getattr(provider, "fetch_related_searches", None)
    if fetch_related is None:
        return []
    try:
        related = fetch_related(seed, location_code)
    except RankProviderError as exc:
        logger.info("Related searches failed for %r: %s", seed, exc)
        return []
    return [
        Idea(keyword=normalise(term), source="serp", rationale=f"Related to “{seed}” on Google")
        for term in related[:limit]
        if normalise(term) and normalise(term) != normalise(seed)
    ]


def merge(*groups: List[Idea]) -> List[Idea]:
    """First source wins on a duplicate, so Search Console's measured numbers
    are never overwritten by an AI guess for the same phrase."""
    seen = {}
    for group in groups:
        for idea in group:
            if idea.keyword and idea.keyword not in seen:
                seen[idea.keyword] = idea
    return list(seen.values())
