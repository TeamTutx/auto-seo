"""AI-suggested keyword opportunities (Signal roadmap Phase C - plan.md).
Given a page, the keyword it's tracking, and who's currently outranking it
for that keyword (already-fetched SERP competitor data - no extra external
lookups beyond what keyword competitor comparison already does), ask the AI
what related keywords/topics would help this page close the gap.
"""
from typing import List

from app.services.ai_providers import get_ai_provider
from app.services.ai_suggestions import _extract_context
from app.services.rank_providers.base import SerpResult

MAX_COMPETITORS_IN_PROMPT = 5

SYSTEM_PROMPT = (
    "You are an SEO strategist. You will be given a page's own content, the "
    "keyword it's targeting, and the titles of pages currently outranking it "
    "for that keyword. Reply with ONLY a list of 3-5 additional keyword or "
    "topic opportunities this page should target to close the gap with "
    "competitors - no preamble, no explanation - one per line, formatted "
    "exactly as '<keyword> - <one sentence reason>'. Do not repeat the "
    "original keyword. Keep each keyword short (2-6 words) and each reason "
    "under 15 words."
)


def _parse_opportunity_lines(raw: str) -> List[dict]:
    results = []
    for line in raw.splitlines():
        line = line.strip().lstrip("-*").strip()
        if not line:
            continue
        if " - " in line:
            keyword, reason = line.split(" - ", 1)
        elif ":" in line:
            keyword, reason = line.split(":", 1)
        else:
            keyword, reason = line, ""
        keyword = keyword.strip()
        if keyword:
            results.append({"keyword": keyword, "reason": reason.strip()})
    return results


def generate_keyword_opportunities(
    html: str, page_url: str, keyword: str, competitors: List[SerpResult]
) -> List[dict]:
    title, content = _extract_context(html)
    competitor_lines = (
        "\n".join(f"- {c.title}" for c in competitors[:MAX_COMPETITORS_IN_PROMPT]) or "(none found)"
    )
    user_prompt = (
        f"Page URL: {page_url}\n"
        f"Page title: {title}\n"
        f'Currently targeting: "{keyword}"\n'
        f'Competitor pages outranking this one for "{keyword}":\n{competitor_lines}\n\n'
        f"Page content (truncated):\n{content}\n\n"
        "Suggest keyword opportunities now."
    )

    provider = get_ai_provider()
    raw = provider.complete(SYSTEM_PROMPT, user_prompt, max_tokens=300).strip()
    return _parse_opportunity_lines(raw)
