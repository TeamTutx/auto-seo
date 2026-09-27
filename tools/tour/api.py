"""Run Signal's API for the product tour: real code, invented vendors.

**Both paid vendors are stubbed.** An AI suggestion is an OpenAI call and a rank
check is a SerpApi search, and neither is worth spending the owner's money to
fill a screenshot. Stubbing only the AI half was not enough - a single keyword
added while setting the tour up spent two real searches before anyone noticed,
which is exactly the kind of thing a comment cannot prevent and a stub can.

Nothing else is faked - the audits, the scoring, the credit ledger, the change
compiler and both write targets are the real implementations, which is the
point: a tour of mocked output would be a drawing of the product, not the
product.

    DATABASE_URL=sqlite:///tour.db python tools/tour/api.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))

from app.services import (  # noqa: E402
    ai_suggestions, competitors, index_status, keyword_discovery, keyword_opportunities,
    keyword_rank_runner, visibility,
)
from app.services.ai_providers import AIProvider  # noqa: E402
from app.services.rank_providers.base import RankProvider, SerpResult  # noqa: E402

ORIGIN = "http://fernandfox.localhost:8901"
TITLE = "Speciality Coffee Roasted in Bristol | Fern & Fox"
META = (
    "Small-batch speciality coffee roasted in Bristol and shipped the next day. Six single origins "
    "and two blends, each labelled with farm, altitude and roast date."
)
SCHEMA = (
    '{"@type": "LocalBusiness", "name": "Fern & Fox Coffee Roasters", '
    '"description": "Small-batch speciality coffee roastery in Bristol.", '
    '"address": {"@type": "PostalAddress", "addressLocality": "Bristol", "addressCountry": "GB"}}'
)
ALT = "1. Roasted coffee beans cooling in the drum\n2. The roastery on a Bristol side street"
PLAN = (
    "- Open the page by saying what speciality coffee is and that you roast it in Bristol, which is "
    "how all three pages above you begin.\n"
    "- Put Bristol in the title tag and meta description; none of yours mention the city.\n"
    "- Give each of the six single origins its own heading with tasting notes, farm and altitude.\n"
    "- Add a short FAQ answering what makes a coffee speciality grade, which is what the AI Overview quoted.\n"
    "- Link the wholesale paragraph to a dedicated wholesale page so it can rank on its own."
)


class TourProvider(AIProvider):
    name = "tour"

    def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 300) -> str:
        p = system_prompt.lower()
        if "title tag" in p:
            return TITLE
        if "meta description" in p:
            return META
        if "structured data" in p or "schema.org" in p:
            return SCHEMA
        if "alt text" in p:
            return ALT
        return PLAN


#: Plausible positions so a rank chart has a shape, keyed by country so the tour
#: can show the same keyword tracked in two markets.
RANKS = {(2356, "desktop"): 14, (2840, "desktop"): 38, (2356, "mobile"): 19}


class TourRanks(RankProvider):
    """`fetch_serp` is the one real vendor call - everything else in the base
    class derives from it - so stubbing it is enough to stop any paid search."""
    name = "tour"

    def fetch_serp(self, keyword, location_code, language_code, device, num_results=100):
        position = RANKS.get((location_code, device), 27)
        competitors = [
            (1, "Bristol's best speciality coffee, ranked", "thebristolist.example"),
            (2, "Where to buy speciality coffee in Bristol", "coffeeguide.example"),
            (3, "Speciality coffee: what the grade actually means", "beanjournal.example"),
        ]
        results = [
            SerpResult(position=pos, title=title, domain=domain, url=f"https://{domain}/")
            for pos, title, domain in competitors
            if pos != position
        ]
        results.append(SerpResult(
            position=position,
            title="Fern & Fox Coffee Roasters",
            domain="fernandfox.localhost:8901",
            url=f"{ORIGIN}/",
        ))
        return sorted(results, key=lambda r: r.position)[:num_results]


_ai = lambda: TourProvider()
_ranks = lambda: TourRanks()

ai_suggestions.get_ai_provider = _ai
keyword_opportunities.get_ai_provider = _ai

# Every module that reaches a paid search, not just the obvious one: each holds
# its own reference from `from ... import get_rank_provider`, so patching the
# package alone would leave real calls going out from the others.
for module in (keyword_rank_runner, competitors, visibility, index_status, keyword_discovery):
    if hasattr(module, "get_rank_provider"):
        module.get_rank_provider = _ranks

if __name__ == "__main__":
    import uvicorn

    print("tour API on :8000")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="warning")
