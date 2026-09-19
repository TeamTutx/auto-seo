"""Did this site show up for this keyword - in Google, and in AI answers?

Three engines, one question each:

- **google** - does the domain appear in the organic results, and where?
- **google_ai_overview** - when Google answered with an AI Overview, did it
  cite this site? Being cited by the box above the results is increasingly more
  valuable than ranking below it.
- **chatgpt** - asked the keyword as a question, does the model's answer mention
  this brand at all?

An honest caveat about the last one, which the UI repeats rather than hides: the
completion API answers from what the model already knows, so this measures
whether a brand has made it into the model's picture of a topic. It is not a
claim about what ChatGPT's live browsing would cite today. That is still the
question worth asking - it just isn't the same question as a Google ranking.

Google organic and the AI Overview come out of a single search, so together they
cost one credit; ChatGPT is a second.
"""
import logging
import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

from app.services.ai_providers import AIProviderError, get_ai_provider
from app.services.rank_providers import get_rank_provider
from app.services.rank_providers.base import RankProviderError, normalize_domain

logger = logging.getLogger("signal.visibility")

GOOGLE = "google"
AI_OVERVIEW = "google_ai_overview"
CHATGPT = "chatgpt"
ENGINES = (GOOGLE, AI_OVERVIEW, CHATGPT)

NO_AI_OVERVIEW = "No AI Overview for this search"

ASK_SYSTEM_PROMPT = (
    "Answer the user's question the way you normally would, as if they typed it "
    "into a chat assistant. Name specific products, tools or companies where "
    "that is genuinely the most useful answer. Keep it under 200 words."
)


@dataclass
class EngineResult:
    engine: str
    present: bool
    position: Optional[int] = None
    detail: Optional[str] = None


def brand_terms(domain: str) -> List[str]:
    """What counts as "us" in a block of prose. The domain's own label plus its
    hyphen/space variants - deliberately not the first word of a hyphenated
    name, because a site called signal-seo.in would otherwise match every
    sentence containing "signal"."""
    host = normalize_domain(domain) or domain.lower()
    label = host.split(".")[0]
    variants = {host, label}
    if "-" in label:
        variants.add(label.replace("-", " "))
        variants.add(label.replace("-", ""))
    return sorted(t for t in variants if len(t) >= 4)


def mentions(text: str, terms: List[str]) -> Optional[str]:
    """The sentence that named us, or None. Returning the sentence rather than a
    bare boolean is what makes the result checkable by a human."""
    if not text:
        return None
    for term in terms:
        match = re.search(rf"[^.!?\n]*\b{re.escape(term)}\b[^.!?\n]*[.!?]?", text, flags=re.IGNORECASE)
        if match:
            return match.group(0).strip()[:300]
    return None


def check_google(keyword: str, domain: str, location_code: int = 2356,
                 device: str = "desktop") -> List[EngineResult]:
    """One search, two answers: the organic position and the AI Overview."""
    target = normalize_domain(domain)
    snapshot = get_rank_provider().fetch_snapshot(
        keyword=keyword, location_code=location_code, language_code="en", device=device,
    )

    position = next((r.position for r in snapshot.results if r.domain == target), None)
    organic = EngineResult(
        engine=GOOGLE,
        present=position is not None,
        position=position,
        detail=None if position is not None else "Not in the first 100 results",
    )

    overview = snapshot.ai_overview
    if overview is None or not overview.present:
        ai = EngineResult(engine=AI_OVERVIEW, present=False, detail=NO_AI_OVERVIEW)
    elif target in overview.sources:
        ai = EngineResult(engine=AI_OVERVIEW, present=True, detail="Cited as a source")
    else:
        cited = ", ".join(dict.fromkeys(overview.sources[:3])) or "no sources listed"
        ai = EngineResult(engine=AI_OVERVIEW, present=False, detail=f"Cited instead: {cited}")
    return [organic, ai]


def check_chatgpt(keyword: str, domain: str) -> EngineResult:
    try:
        answer = get_ai_provider().complete(ASK_SYSTEM_PROMPT, keyword, max_tokens=400)
    except AIProviderError as exc:
        logger.info("AI visibility check failed for %r: %s", keyword, exc)
        return EngineResult(engine=CHATGPT, present=False, detail=f"Could not ask the model: {exc}"[:300])

    sentence = mentions(answer, brand_terms(domain))
    if sentence:
        return EngineResult(engine=CHATGPT, present=True, detail=sentence)
    return EngineResult(engine=CHATGPT, present=False, detail="Not mentioned in the answer")


def check_keyword(keyword: str, domain: str, location_code: int = 2356,
                  device: str = "desktop", include_ai: bool = True) -> List[EngineResult]:
    """Everything known about one keyword. A vendor failing on one engine must
    not lose the other - a SerpApi outage shouldn't wipe the ChatGPT reading."""
    results: List[EngineResult] = []
    try:
        results.extend(check_google(keyword, domain, location_code, device))
    except RankProviderError as exc:
        logger.info("Google visibility check failed for %r: %s", keyword, exc)
        results.append(EngineResult(engine=GOOGLE, present=False, detail=f"Search failed: {exc}"[:300]))
    if include_ai:
        results.append(check_chatgpt(keyword, domain))
    return results
