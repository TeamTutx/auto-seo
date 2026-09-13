"""On-page SEO audit engine (REQUIREMENTS.md §2.2).

Pure, network-free once given HTML: fetch is the caller's job (see
app.services.fetcher), so this module is trivial to unit test against
fixture HTML and safe to run inside a Celery task or a request handler.
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.models import CheckStatus

TITLE_MIN_LEN = 30
TITLE_MAX_LEN = 60
META_DESC_MIN_LEN = 120
META_DESC_MAX_LEN = 160
THIN_CONTENT_WORDS = 300
KEYWORD_DENSITY_MIN = 0.5  # percent
KEYWORD_DENSITY_MAX = 3.0  # percent


@dataclass
class CheckResult:
    check_type: str
    status: CheckStatus
    message: str
    suggested_fix: Optional[str] = None


@dataclass
class AuditResult:
    score: int
    extracted_title: Optional[str]
    word_count: int
    checks: List[CheckResult] = field(default_factory=list)


def _domain(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _count_syllables(word: str) -> int:
    word = word.lower().strip(".,!?;:\"'()")
    if not word:
        return 0
    vowel_groups = re.findall(r"[aeiouy]+", word)
    count = len(vowel_groups)
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def _flesch_reading_ease(text: str) -> Optional[float]:
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    words = re.findall(r"[A-Za-z']+", text)
    if not sentences or not words:
        return None
    syllables = sum(_count_syllables(w) for w in words)
    words_per_sentence = len(words) / len(sentences)
    syllables_per_word = syllables / len(words)
    score = 206.835 - (1.015 * words_per_sentence) - (84.6 * syllables_per_word)
    return round(score, 1)


def _check_title(soup: BeautifulSoup, target_keyword: Optional[str], sibling_titles: Sequence[str]) -> tuple:
    title_tag = soup.title
    title_text = title_tag.get_text(strip=True) if title_tag else None

    if not title_text:
        return CheckResult(
            "title_tag", CheckStatus.fail, "Page is missing a <title> tag.",
            "Add a unique, descriptive <title> tag of 30-60 characters.",
        ), None

    length = len(title_text)
    if length < TITLE_MIN_LEN or length > TITLE_MAX_LEN:
        status = CheckStatus.warning
        message = f"Title is {length} chars (recommended {TITLE_MIN_LEN}-{TITLE_MAX_LEN})."
        fix = "Rewrite the title to fall within 30-60 characters."
    elif target_keyword and target_keyword.lower() not in title_text.lower():
        status = CheckStatus.warning
        message = "Title does not contain the target keyword."
        fix = f'Work "{target_keyword}" naturally into the title.'
    elif any(title_text.strip().lower() == t.strip().lower() for t in sibling_titles):
        status = CheckStatus.fail
        message = "Title duplicates another page's title on this site."
        fix = "Give this page a unique title."
    else:
        status = CheckStatus.pass_
        message = f"Title is present and well-formed ({length} chars)."
        fix = None

    return CheckResult("title_tag", status, message, fix), title_text


def _check_meta_description(soup: BeautifulSoup) -> CheckResult:
    tag = soup.find("meta", attrs={"name": "description"})
    content = tag.get("content", "").strip() if tag else ""

    if not content:
        return CheckResult(
            "meta_description", CheckStatus.fail, "Missing meta description.",
            f"Add a meta description of {META_DESC_MIN_LEN}-{META_DESC_MAX_LEN} characters.",
        )

    length = len(content)
    if length < META_DESC_MIN_LEN or length > META_DESC_MAX_LEN:
        return CheckResult(
            "meta_description", CheckStatus.warning,
            f"Meta description is {length} chars (recommended {META_DESC_MIN_LEN}-{META_DESC_MAX_LEN}).",
            "Adjust the meta description length.",
        )

    return CheckResult("meta_description", CheckStatus.pass_, f"Meta description is well-formed ({length} chars).")


def _check_headings(soup: BeautifulSoup) -> CheckResult:
    h1_tags = soup.find_all("h1")
    if len(h1_tags) == 0:
        return CheckResult(
            "heading_structure", CheckStatus.fail, "No H1 tag found.",
            "Add exactly one H1 describing the page's main topic.",
        )
    if len(h1_tags) > 1:
        return CheckResult(
            "heading_structure", CheckStatus.warning,
            f"Found {len(h1_tags)} H1 tags; expected exactly one.",
            "Keep a single H1 per page and demote the rest to H2/H3.",
        )

    levels = [int(tag.name[1]) for tag in soup.find_all(re.compile(r"^h[1-6]$"))]
    skipped = any(b - a > 1 for a, b in zip(levels, levels[1:]))
    if skipped:
        return CheckResult(
            "heading_structure", CheckStatus.warning,
            "Heading levels skip a level (e.g. H2 to H4).",
            "Keep heading levels sequential for a clear document outline.",
        )

    return CheckResult("heading_structure", CheckStatus.pass_, "Exactly one H1 and a sequential heading hierarchy.")


def _check_image_alt_text(soup: BeautifulSoup) -> CheckResult:
    images = soup.find_all("img")
    if not images:
        return CheckResult("image_alt_text", CheckStatus.pass_, "No images on page.")

    with_alt = sum(1 for img in images if img.get("alt", "").strip())
    coverage = round((with_alt / len(images)) * 100)

    if coverage == 100:
        status = CheckStatus.pass_
    elif coverage >= 50:
        status = CheckStatus.warning
    else:
        status = CheckStatus.fail

    return CheckResult(
        "image_alt_text", status,
        f"{with_alt}/{len(images)} images ({coverage}%) have alt text.",
        None if status == CheckStatus.pass_ else "Add descriptive alt text to every content image.",
    )


def _check_links(soup: BeautifulSoup, page_url: str) -> CheckResult:
    page_domain = _domain(page_url)
    internal, external = 0, 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        link_domain = _domain(href) if href.startswith("http") else page_domain
        if link_domain == page_domain:
            internal += 1
        else:
            external += 1

    if internal == 0:
        return CheckResult(
            "link_analysis", CheckStatus.warning,
            "No internal links found.",
            "Add internal links to related pages to help crawlability and topical authority.",
        )

    return CheckResult("link_analysis", CheckStatus.pass_, f"{internal} internal, {external} external links found.")


def _check_content_and_keyword_density(soup: BeautifulSoup, target_keyword: Optional[str]) -> tuple:
    # Work on a copy: decomposing script/style tags would otherwise mutate the
    # shared soup and break checks that run after this one (e.g. structured_data,
    # which looks for <script type="application/ld+json">).
    content_soup = BeautifulSoup(str(soup), "lxml")
    for tag in content_soup(["script", "style", "noscript"]):
        tag.decompose()
    text = content_soup.get_text(separator=" ", strip=True)
    words = re.findall(r"[A-Za-z']+", text)
    word_count = len(words)

    checks = []

    if word_count < THIN_CONTENT_WORDS:
        checks.append(CheckResult(
            "content_length", CheckStatus.warning,
            f"Only {word_count} words on page (recommended {THIN_CONTENT_WORDS}+).",
            "Expand the content to cover the topic more thoroughly.",
        ))
    else:
        checks.append(CheckResult("content_length", CheckStatus.pass_, f"{word_count} words on page."))

    if target_keyword:
        keyword_words = target_keyword.lower().split()
        occurrences = text.lower().count(target_keyword.lower())
        density = round((occurrences * len(keyword_words) / word_count) * 100, 2) if word_count else 0.0
        if density < KEYWORD_DENSITY_MIN:
            checks.append(CheckResult(
                "keyword_density", CheckStatus.warning,
                f'"{target_keyword}" density is {density}% (recommended {KEYWORD_DENSITY_MIN}-{KEYWORD_DENSITY_MAX}%).',
                "Mention the target keyword a few more times naturally in the content.",
            ))
        elif density > KEYWORD_DENSITY_MAX:
            checks.append(CheckResult(
                "keyword_density", CheckStatus.warning,
                f'"{target_keyword}" density is {density}% (recommended {KEYWORD_DENSITY_MIN}-{KEYWORD_DENSITY_MAX}%).',
                "Reduce repetition of the target keyword to avoid over-optimization.",
            ))
        else:
            checks.append(CheckResult("keyword_density", CheckStatus.pass_, f'"{target_keyword}" density is {density}%.'))

    return checks, word_count, text


def _check_readability(text: str) -> CheckResult:
    score = _flesch_reading_ease(text)
    if score is None:
        return CheckResult("readability", CheckStatus.warning, "Not enough text to score readability.")

    if score >= 60:
        status = CheckStatus.pass_
        message = f"Flesch Reading Ease score: {score} (easy to read)."
        fix = None
    elif score >= 30:
        status = CheckStatus.warning
        message = f"Flesch Reading Ease score: {score} (fairly difficult)."
        fix = "Shorten sentences and use simpler words to improve readability."
    else:
        status = CheckStatus.fail
        message = f"Flesch Reading Ease score: {score} (very difficult)."
        fix = "Rewrite with shorter sentences and simpler vocabulary."

    return CheckResult("readability", status, message, fix)


def _check_canonical(soup: BeautifulSoup) -> CheckResult:
    tag = soup.find("link", attrs={"rel": "canonical"})
    if tag and tag.get("href"):
        return CheckResult("canonical_tag", CheckStatus.pass_, f"Canonical tag present: {tag['href']}.")
    return CheckResult(
        "canonical_tag", CheckStatus.warning, "No canonical tag found.",
        "Add a <link rel=\"canonical\"> pointing to the preferred URL for this page.",
    )


def _check_robots_meta(soup: BeautifulSoup) -> CheckResult:
    tag = soup.find("meta", attrs={"name": "robots"})
    content = tag.get("content", "").lower() if tag else ""

    if tag and ("noindex" in content or "nofollow" in content):
        return CheckResult(
            "robots_meta_tag", CheckStatus.fail,
            f'Robots meta tag blocks indexing/following: "{content}".',
            "Remove noindex/nofollow unless intentionally hiding this page from search engines.",
        )

    return CheckResult("robots_meta_tag", CheckStatus.pass_, "No blocking robots meta directives found.")


def _check_structured_data(soup: BeautifulSoup) -> CheckResult:
    json_ld = soup.find_all("script", attrs={"type": "application/ld+json"})
    microdata = soup.find_all(attrs={"itemtype": True})

    if json_ld or microdata:
        return CheckResult("structured_data", CheckStatus.pass_, "Structured data (schema.org) found on page.")

    return CheckResult(
        "structured_data", CheckStatus.warning, "No structured data found.",
        "Add relevant schema.org JSON-LD (e.g. Article, Product, FAQPage) to improve rich-result eligibility.",
    )


def _score_from_checks(checks: Sequence[CheckResult]) -> int:
    if not checks:
        return 0
    points = {CheckStatus.pass_: 1.0, CheckStatus.warning: 0.5, CheckStatus.fail: 0.0}
    total = sum(points[c.status] for c in checks)
    return round((total / len(checks)) * 100)


def run_onpage_audit(
    html: str,
    page_url: str,
    target_keyword: Optional[str] = None,
    sibling_titles: Sequence[str] = (),
) -> AuditResult:
    soup = BeautifulSoup(html, "lxml")

    checks: List[CheckResult] = []

    title_check, extracted_title = _check_title(soup, target_keyword, sibling_titles)
    checks.append(title_check)
    checks.append(_check_meta_description(soup))
    checks.append(_check_headings(soup))
    checks.append(_check_image_alt_text(soup))
    checks.append(_check_links(soup, page_url))

    content_checks, word_count, text = _check_content_and_keyword_density(soup, target_keyword)
    checks.extend(content_checks)
    checks.append(_check_readability(text))
    checks.append(_check_canonical(soup))
    checks.append(_check_robots_meta(soup))
    checks.append(_check_structured_data(soup))

    return AuditResult(
        score=_score_from_checks(checks),
        extracted_title=extracted_title,
        word_count=word_count,
        checks=checks,
    )
