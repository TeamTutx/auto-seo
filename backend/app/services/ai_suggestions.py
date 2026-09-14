"""AI-generated suggestions (REQUIREMENTS.md §2.2, §2.7). Currently just
meta descriptions; add a sibling function per suggestion type as they're
needed, each building its own prompt and calling get_ai_provider().complete.
"""
import re
from typing import Optional, Tuple

from bs4 import BeautifulSoup

from app.services.ai_providers import get_ai_provider

MAX_CONTENT_CHARS = 3000

META_DESCRIPTION_SYSTEM_PROMPT = (
    "You are an SEO copywriter. Reply with ONLY the meta description text - "
    "no quotes, no preamble, no explanation, no markdown. It must be between "
    "120 and 160 characters, accurately summarize the page for a search "
    "results snippet, and naturally include the target keyword if one is "
    "given."
)

TITLE_TAG_SYSTEM_PROMPT = (
    "You are an SEO copywriter. Reply with ONLY the title tag text - no "
    "quotes, no preamble, no explanation, no markdown. It must be between "
    "30 and 60 characters, accurately describe the page, and naturally "
    "include the target keyword near the start if one is given."
)


def _extract_context(html: str) -> Tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True)).strip()

    return title, text[:MAX_CONTENT_CHARS]


def generate_meta_description(html: str, page_url: str, target_keyword: Optional[str]) -> str:
    title, content = _extract_context(html)
    keyword_line = f"Target keyword: {target_keyword}\n" if target_keyword else ""
    user_prompt = (
        f"Page URL: {page_url}\n"
        f"Page title: {title}\n"
        f"{keyword_line}"
        f"Page content (truncated):\n{content}\n\n"
        "Write the meta description now."
    )

    provider = get_ai_provider()
    return provider.complete(META_DESCRIPTION_SYSTEM_PROMPT, user_prompt, max_tokens=120).strip()


def generate_title_tag(html: str, page_url: str, target_keyword: Optional[str]) -> str:
    title, content = _extract_context(html)
    keyword_line = f"Target keyword: {target_keyword}\n" if target_keyword else ""
    user_prompt = (
        f"Page URL: {page_url}\n"
        f"Current title tag (if any): {title or '(none)'}\n"
        f"{keyword_line}"
        f"Page content (truncated):\n{content}\n\n"
        "Write a new title tag now."
    )

    provider = get_ai_provider()
    return provider.complete(TITLE_TAG_SYSTEM_PROMPT, user_prompt, max_tokens=60).strip()
