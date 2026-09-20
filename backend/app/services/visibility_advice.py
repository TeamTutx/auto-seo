"""How to actually become visible for one keyword.

The hard part of advice like this is that generic SEO guidance is worthless -
"improve your content quality" helps nobody. So every suggestion here is built
from things Signal has actually measured for this exact keyword:

- where the site ranks, and the pages that outrank it (titles and URLs)
- whether Google's AI Overview cited the site, and which sources it used instead
- whether an AI assistant named the site, and what it said instead
- the site's own candidate page - its real content - and what else it publishes

The model is told to reference that evidence and is given nothing else to work
from, which is what keeps the output specific. It is still a language model
writing SEO advice, so the UI presents it as suggestions rather than fact.

Costs one credit: the search was already paid for by the visibility check that
captured the evidence, so this is a single model call.
"""
import json
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.services.ai_providers import AIProviderError, get_ai_provider

logger = logging.getLogger("signal.visibility")

MAX_ACTIONS = 5
ADDRESSES = ("google", "ai", "both")

SYSTEM_PROMPT = (
    "You are an SEO strategist advising the owner of a specific website about a "
    "specific search. You are given real measurements: where their site ranks, "
    "which pages outrank it, whether Google's AI Overview and an AI assistant "
    "mentioned them, and the content of their own most relevant page.\n\n"
    "Rules:\n"
    "1. Every action must reference something in the data - a competitor that "
    "ranks, a source the AI Overview cited, something their page is missing. "
    "Generic advice like 'improve content quality' or 'build backlinks' is "
    "useless and must not appear.\n"
    "2. Never invent numbers, search volumes, traffic estimates or facts about "
    "competitors beyond what you are shown.\n"
    "3. If the right answer is that they need a new page, say so and describe "
    "what it should cover.\n"
    "4. Getting cited by AI answers and ranking in Google are different "
    "problems; say which one each action addresses.\n"
    "5. Write for someone who will do the work today. Be concrete and brief.\n\n"
    'Reply with JSON only: {"diagnosis": "1-2 sentences on why they are not '
    'visible", "target_page": "the URL that should rank, or null if they need a '
    'new page", "actions": [{"title": "short imperative", "detail": "what to do '
    'and why, referencing the evidence", "addresses": "google|ai|both"}]}'
)


@dataclass
class Advice:
    diagnosis: str
    actions: List[dict]
    target_page_url: Optional[str]


def _fmt_google(reading: Optional[dict], context: Optional[dict]) -> str:
    if reading is None:
        return "Google: not checked."
    if reading.get("position"):
        line = f"Google: this site ranks #{reading['position']}."
    else:
        line = "Google: this site does not appear in the first 100 results."
    top = (context or {}).get("top_results") or []
    if top:
        listed = "\n".join(f"  #{r['position']} {r['title']} ({r['domain']})" for r in top)
        line += f"\nPages that rank for it:\n{listed}"
    return line


def _fmt_ai_overview(reading: Optional[dict], context: Optional[dict]) -> str:
    if reading is None:
        return "Google AI Overview: not checked."
    if reading.get("detail", "").startswith("No AI Overview"):
        return "Google AI Overview: Google did not show an AI answer for this search."
    sources = (context or {}).get("sources") or []
    who = ", ".join(sources[:5]) if sources else "none listed"
    if reading.get("present"):
        return f"Google AI Overview: this site IS cited. Other sources: {who}."
    answer = (context or {}).get("answer") or ""
    out = f"Google AI Overview: shown, but this site is NOT cited. It cited: {who}."
    if answer:
        out += f'\n  What the AI answer said: "{answer[:600]}"'
    return out


def _fmt_assistant(reading: Optional[dict], context: Optional[dict]) -> str:
    if reading is None:
        return "AI assistant: not checked."
    answer = (context or {}).get("answer") or ""
    if reading.get("present"):
        return f"AI assistant: names this site. It said: \"{reading.get('detail', '')}\""
    out = "AI assistant: asked this as a question, it does NOT name this site."
    if answer:
        out += f'\n  What it answered instead: "{answer[:600]}"'
    return out


def build_prompt(
    *,
    keyword: str,
    domain: str,
    readings: Dict[str, dict],
    contexts: Dict[str, dict],
    page_url: Optional[str],
    page_title: Optional[str],
    page_content: Optional[str],
    other_pages: List[dict],
) -> str:
    def _page_line(page: dict) -> str:
        title = page.get("title")
        return f"  {page['url']}" + (f" - {title}" if title else "")

    pages = "\n".join(_page_line(p) for p in other_pages[:20])
    own = "This site has no pages tracked yet."
    if page_url:
        own = f"Their most relevant page: {page_url}"
        if page_title:
            own += f"\nIts title: {page_title}"
        if page_content:
            own += f"\nIts content (truncated):\n{page_content[:4000]}"

    return (
        f'Keyword: "{keyword}"\n'
        f"Their site: {domain}\n\n"
        f"{_fmt_google(readings.get('google'), contexts.get('google'))}\n\n"
        f"{_fmt_ai_overview(readings.get('google_ai_overview'), contexts.get('google_ai_overview'))}\n\n"
        f"{_fmt_assistant(readings.get('chatgpt'), contexts.get('chatgpt'))}\n\n"
        f"{own}\n\n"
        f"Every page they publish:\n{pages or '  (none)'}\n\n"
        "Give the advice now."
    )


def best_page(keyword: str, pages: List[dict]) -> Optional[dict]:
    """The page most likely meant to rank for this keyword, by how much of the
    keyword appears in its URL and title. A weak heuristic on purpose: the model
    is also shown every page and told it may recommend a different one, or a new
    one. The point is to give it one page's actual *content* to work from."""
    words = [w for w in re.split(r"\W+", keyword.lower()) if len(w) > 2]
    if not pages:
        return None

    def score(page: dict) -> tuple:
        haystack = f"{page.get('url', '')} {page.get('title') or ''}".lower()
        hits = sum(1 for w in words if w in haystack)
        # Ties go to the shallowest URL - the home page beats a deep one.
        return (hits, -page.get("url", "").count("/"))

    ranked = max(pages, key=score)
    return ranked if score(ranked)[0] > 0 else pages[0]


def parse(raw: str) -> Optional[Advice]:
    """Models wrap JSON in prose or fences often enough that finding the object
    beats insisting the whole reply parses."""
    match = re.search(r"\{.*\}", raw or "", flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None

    actions = []
    for entry in (data.get("actions") or [])[:MAX_ACTIONS]:
        if not isinstance(entry, dict):
            continue
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        addresses = (entry.get("addresses") or "both").strip().lower()
        actions.append({
            "title": title[:120],
            "detail": (entry.get("detail") or "").strip()[:600],
            "addresses": addresses if addresses in ADDRESSES else "both",
        })
    diagnosis = (data.get("diagnosis") or "").strip()
    if not diagnosis and not actions:
        return None

    target = data.get("target_page")
    return Advice(
        diagnosis=diagnosis[:600] or "No single cause stood out.",
        actions=actions,
        target_page_url=target.strip() if isinstance(target, str) and target.strip() else None,
    )


def generate(**kwargs) -> Optional[Advice]:
    try:
        raw = get_ai_provider().complete(SYSTEM_PROMPT, build_prompt(**kwargs), max_tokens=900)
    except AIProviderError as exc:
        logger.info("visibility advice failed for %r: %s", kwargs.get("keyword"), exc)
        return None
    return parse(raw)
