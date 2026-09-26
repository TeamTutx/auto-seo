"""AI-generated suggestions (REQUIREMENTS.md §2.2, §2.7). One function per
suggestion type, each building its own prompt and calling
get_ai_provider().complete.
"""
import json
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup

from app.services.ai_providers import get_ai_provider

MAX_CONTENT_CHARS = 3000
MAX_ALT_TEXT_IMAGES = 8

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

HEADING_SYSTEM_PROMPT = (
    "You are an SEO editor. Reply with ONLY a heading outline - no preamble, "
    "no explanation, no markdown formatting other than plain text lines. "
    "Give exactly one H1 line prefixed 'H1: ' describing the page's main "
    "topic, followed by 2-5 H2 lines prefixed 'H2: ' for logical subsections "
    "the content already covers. Naturally include the target keyword in "
    "the H1 if one is given."
)

READABILITY_SYSTEM_PROMPT = (
    "You are an editor who simplifies writing. Reply with ONLY the rewritten "
    "text - no preamble, no explanation, no markdown, no quotes. Rewrite the "
    "given opening passage using shorter sentences and simpler words while "
    "keeping the same meaning and any target keyword."
)

ALT_TEXT_SYSTEM_PROMPT = (
    "You are an accessibility and SEO expert writing image alt text. You "
    "will be given a numbered list of images, each with whatever context "
    "(surrounding text or filename) is available. Reply with ONLY one line "
    "per image, in the same order, formatted exactly as '<number>. <alt "
    "text>' - concise (under 125 characters), descriptive, and not starting "
    "with \"image of\" or \"picture of\"."
)

STRUCTURED_DATA_SYSTEM_PROMPT = (
    "You are a technical SEO adding schema.org structured data to a page. Reply "
    "with ONLY a single JSON object - no markdown fences, no preamble, no "
    "explanation. It must have @context \"https://schema.org\" and an @type that "
    "genuinely fits what the page is (Article, BlogPosting, Product, FAQPage, "
    "Organization, WebPage). Fill only properties the page content actually "
    "supports: never invent an author, a date, a price, a rating or a review. "
    "Structured data that describes something not visible on the page is a "
    "manual-action risk, so when in doubt leave the property out."
)

INTERNAL_LINKING_SYSTEM_PROMPT = (
    "You are an SEO strategist suggesting internal links. Reply with ONLY a "
    "short list - no preamble, no explanation - of 2-4 suggestions, one per "
    "line, each formatted exactly as 'Link to <url> using anchor text like "
    "\"<anchor text>\"'. Pick pages from the candidate list that are "
    "topically relevant to the page being edited."
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


def generate_heading_suggestion(html: str, page_url: str, target_keyword: Optional[str]) -> str:
    title, content = _extract_context(html)
    keyword_line = f"Target keyword: {target_keyword}\n" if target_keyword else ""
    user_prompt = (
        f"Page URL: {page_url}\n"
        f"Page title: {title}\n"
        f"{keyword_line}"
        f"Page content (truncated):\n{content}\n\n"
        "Suggest a heading outline now."
    )

    provider = get_ai_provider()
    return provider.complete(HEADING_SYSTEM_PROMPT, user_prompt, max_tokens=150).strip()


def generate_readability_suggestion(html: str, page_url: str, target_keyword: Optional[str]) -> str:
    _, content = _extract_context(html)
    keyword_line = f"Target keyword: {target_keyword}\n" if target_keyword else ""
    user_prompt = (
        f"Page URL: {page_url}\n"
        f"{keyword_line}"
        f"Opening passage to simplify:\n{content[:800]}\n\n"
        "Rewrite it now."
    )

    provider = get_ai_provider()
    return provider.complete(READABILITY_SYSTEM_PROMPT, user_prompt, max_tokens=400).strip()


@dataclass
class _ImageForAltText:
    src: str
    context: str


def _extract_images_missing_alt(html: str) -> List[_ImageForAltText]:
    soup = BeautifulSoup(html, "lxml")
    images = []
    for img in soup.find_all("img"):
        if img.get("alt", "").strip():
            continue
        src = img.get("src", "").strip()
        if not src:
            continue
        parent_text = img.parent.get_text(" ", strip=True) if img.parent else ""
        context = parent_text[:200] or src.rsplit("/", 1)[-1]
        images.append(_ImageForAltText(src=src, context=context))
        if len(images) >= MAX_ALT_TEXT_IMAGES:
            break
    return images


def _parse_numbered_lines(raw: str, expected: int) -> List[str]:
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^\d+[.)]\s*(.+)$", line)
        lines.append(match.group(1).strip() if match else line)
    return lines[:expected]


def generate_alt_text_suggestions(html: str, page_url: str) -> List[dict]:
    """One suggestion per <img> missing alt text (up to MAX_ALT_TEXT_IMAGES),
    batched into a single AI call rather than one call per image."""
    images = _extract_images_missing_alt(html)
    if not images:
        return []

    title, _ = _extract_context(html)
    listing = "\n".join(f"{i + 1}. src: {img.src}\n   context: {img.context}" for i, img in enumerate(images))
    user_prompt = (
        f"Page URL: {page_url}\n"
        f"Page title: {title}\n"
        f"Images:\n{listing}\n\n"
        "Suggest alt text for each image now."
    )

    provider = get_ai_provider()
    raw = provider.complete(ALT_TEXT_SYSTEM_PROMPT, user_prompt, max_tokens=40 * len(images)).strip()
    alt_texts = _parse_numbered_lines(raw, len(images))

    return [
        {"src": img.src, "suggested_alt": alt_texts[i] if i < len(alt_texts) else ""}
        for i, img in enumerate(images)
    ]


def generate_internal_linking_suggestions(
    html: str, page_url: str, candidate_pages: List[Tuple[str, Optional[str]]]
) -> str:
    title, content = _extract_context(html)
    candidates = "\n".join(
        f"- {url}" + (f" (target keyword: {kw})" if kw else "") for url, kw in candidate_pages
    )
    user_prompt = (
        f"Page URL: {page_url}\n"
        f"Page title: {title}\n"
        f"Page content (truncated):\n{content}\n\n"
        f"Candidate pages on the same site to link to:\n{candidates}\n\n"
        "Suggest internal links now."
    )

    provider = get_ai_provider()
    return provider.complete(INTERNAL_LINKING_SYSTEM_PROMPT, user_prompt, max_tokens=200).strip()


def generate_structured_data(html: str, page_url: str, target_keyword: Optional[str]) -> Optional[str]:
    """A JSON-LD block for a page that has none.

    Returns None rather than a broken block when the model's reply is not valid
    JSON: invalid structured data is worse than none, because Google reports it
    as an error against the page. The output is re-serialised from the parsed
    object, so what gets written is formatted consistently rather than however
    the model happened to indent it."""
    title, content = _extract_context(html)
    keyword_line = f"Target keyword: {target_keyword}\n" if target_keyword else ""
    user_prompt = (
        f"Page URL: {page_url}\n"
        f"Page title: {title}\n"
        f"{keyword_line}"
        f"Page content (truncated):\n{content}\n\n"
        "Write the JSON-LD object now."
    )

    provider = get_ai_provider()
    raw = provider.complete(STRUCTURED_DATA_SYSTEM_PROMPT, user_prompt, max_tokens=600).strip()

    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(parsed, dict) or "@type" not in parsed:
        return None
    parsed.setdefault("@context", "https://schema.org")
    return json.dumps(parsed, indent=2, ensure_ascii=False)
