"""Run Signal's API for the product tour: real code, invented vendors.

Every AI suggestion in Signal is a paid OpenAI call, so the tour stubs the
provider rather than spending the owner's money to fill a screenshot. Nothing
else is faked - the audits, the scoring, the credit ledger, the change compiler
and both write targets are the real implementations, which is the point: a tour
that showed mocked output would be a drawing of the product, not the product.

    DATABASE_URL=sqlite:///tour.db python tools/tour/api.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))

from app.services import ai_suggestions, keyword_opportunities  # noqa: E402
from app.services.ai_providers import AIProvider  # noqa: E402

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


_provider = lambda: TourProvider()
ai_suggestions.get_ai_provider = _provider
keyword_opportunities.get_ai_provider = _provider

if __name__ == "__main__":
    import uvicorn

    print("tour API on :8000")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="warning")
