"""AI-suggested keyword opportunities (Signal roadmap Phase C - plan.md).
Given a page, the keyword it's tracking, and who's currently outranking it
for that keyword (already-fetched SERP competitor data - no extra external
lookups beyond what keyword competitor comparison already does), ask the AI
what related keywords/topics would help this page close the gap.

generate_ranking_action_plan below is the sibling feature for a keyword that
isn't ranking (or ranking poorly) at all: instead of suggesting OTHER
keywords, it suggests concrete changes to help the page start ranking for
THIS exact keyword.
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

ACTION_PLAN_SYSTEM_PROMPT = (
    "You are an SEO strategist. You will be given a page's own content, a "
    "keyword it wants to rank for but currently doesn't rank at all (or "
    "ranks poorly) for, and the titles of pages that DO rank for it. Reply "
    "with ONLY a short action plan - no preamble, no explanation - of 3-5 "
    "concrete steps this exact page should take to start ranking for that "
    "exact keyword, one per line, each starting with a verb. Be specific "
    "about what the top-ranking pages cover that this page doesn't, rather "
    "than generic SEO advice."
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


def generate_ranking_action_plan(html: str, page_url: str, keyword: str, competitors: List[SerpResult]) -> str:
    title, content = _extract_context(html)
    competitor_lines = (
        "\n".join(f"- {c.title}" for c in competitors[:MAX_COMPETITORS_IN_PROMPT])
        or "(none found - this may be a low-competition keyword worth targeting directly)"
    )
    user_prompt = (
        f"Page URL: {page_url}\n"
        f"Page title: {title}\n"
        f'Target keyword (not ranking, or ranking poorly): "{keyword}"\n'
        f"Top-ranking pages for this keyword:\n{competitor_lines}\n\n"
        f"Page content (truncated):\n{content}\n\n"
        "Write the action plan now."
    )

    provider = get_ai_provider()
    return provider.complete(ACTION_PLAN_SYSTEM_PROMPT, user_prompt, max_tokens=300).strip()
