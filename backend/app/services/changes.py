"""Turn a suggestion into an exact edit.

Everything Signal suggests is already generated somewhere; what it has never
produced is a *change* - this field, on this page, from this value to that one.
Prose cannot be applied. "Answer the question in your first paragraph, like the
pages that outrank you" is good advice and there is nothing software can do with
it. So this module is the narrow waist: a suggestion goes in, and either a
ProposedChange comes out or the suggestion stays advice.

Three groups, and the split is the point:

- **Deterministic.** `canonical_tag` is the page's own URL; `robots_meta_tag` is
  the current value with the blocking directives removed. No model runs and no
  credit is charged, because there is nothing to pay for. These are also two of
  the three checks that have never had a fix button at all.
- **One model call, one bounded value.** `title_tag`, `meta_description`,
  `structured_data`, and `image_alt_text` (one call for every image on the page,
  as the existing alt-text endpoint already does - so one credit, not one per
  image).
- **Refused.** Everything that edits prose: `content_length`, `readability`,
  `keyword_density`, `heading_structure`, `link_analysis`. `compile_field` raises
  Unsupported for these, and the caller shows the existing advice instead. The
  reason is not effort: setting a tag wrongly produces a wrong tag, while
  rewriting a paragraph wrongly produces a page that no longer says what the
  business meant.

`before` always comes from the live page, fetched here, never from a stored audit
- an audit can be days old, and writing over a value the owner has since changed
is the one mistake in this feature that loses their work rather than Signal's.
"""
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from sqlmodel import Session, select

from app.models import APPLICABLE_FIELDS, ChangeStatus, Page, ProposedChange
from app.services import ai_suggestions, audit_engine
from app.services.ai_providers import AIProviderError

logger = logging.getLogger("signal.changes")

DETERMINISTIC_FIELDS = ("canonical_tag", "robots_meta_tag")

# Why a field is advice rather than a change, in words the UI can show.
NOT_APPLICABLE = {
    "heading_structure": "Restructuring headings edits the page's content, so Signal drafts the outline for you to apply.",
    "readability": "Rewriting the copy edits the page's content, so Signal drafts it for you to apply.",
    "content_length": "Only you can decide what a longer page should say, so Signal drafts suggestions instead.",
    "keyword_density": "Changing how often a phrase appears means editing the copy, so Signal drafts it instead.",
    "link_analysis": "Adding a link means choosing where in the copy it belongs, so Signal suggests the link and anchor instead.",
}

_BLOCKING_ROBOTS = ("noindex", "nofollow", "none")


class Unsupported(Exception):
    """This field is advice, not a change. Carries the sentence to show."""


class NothingToChange(Exception):
    """The page is already correct for this field, so there is no edit to make."""


@dataclass
class Compiled:
    changes: List[ProposedChange]
    credits: int  # model calls made, so 0 for a deterministic field


# --- reading the current value off the live page ---


def read_current(html: str, field: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    if field == "title_tag":
        return soup.title.get_text(strip=True) if soup.title else None
    if field == "meta_description":
        tag = soup.find("meta", attrs={"name": "description"})
        value = (tag.get("content") or "").strip() if tag else ""
        return value or None
    if field == "canonical_tag":
        tag = soup.find("link", attrs={"rel": lambda v: v and "canonical" in [x.lower() for x in (v if isinstance(v, list) else [v])]})
        value = (tag.get("href") or "").strip() if tag else ""
        return value or None
    if field == "robots_meta_tag":
        tag = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
        value = (tag.get("content") or "").strip() if tag else ""
        return value or None
    if field == "structured_data":
        block = soup.find("script", attrs={"type": re.compile(r"application/ld\+json", re.I)})
        return block.string.strip() if block and block.string else None
    return None


def current_alt(html: str, src: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    for img in soup.find_all("img"):
        if (img.get("src") or "").strip() == src:
            return (img.get("alt") or "").strip() or None
    return None


# --- the deterministic two ---


def _canonical(page: Page, before: Optional[str]) -> str:
    """The canonical is the URL Signal and Search Console already agree this page
    is. `page.url` went through _clean_page_url on the way in and preserves the
    site's own trailing-slash choice, so it is exactly the string Google
    canonicalised - which is the entire point of the tag."""
    if before and before.rstrip("/") == page.url.rstrip("/"):
        raise NothingToChange("This page already declares itself canonical.")
    return page.url


def _robots(before: Optional[str]) -> str:
    """Drop only the directives that stop the page being indexed or its links
    followed, and keep everything else the owner put there (max-snippet,
    max-image-preview and the rest are their choices, not mistakes)."""
    if not before:
        raise NothingToChange("This page has no robots meta tag blocking it.")
    kept = [d.strip() for d in before.split(",") if d.strip().lower() not in _BLOCKING_ROBOTS]
    if len(kept) == len([d for d in before.split(",") if d.strip()]):
        raise NothingToChange("This page's robots meta tag is not blocking indexing.")
    # An empty result means every directive was a blocking one, so the whole tag
    # should go. "index, follow" says the same thing as no tag at all and is the
    # safer write: it is a value to set, not a tag to find and delete.
    return ", ".join(kept) if kept else "index, follow"


# --- compiling ---


def compile_field(
    session: Session,
    page: Page,
    field: str,
    html: str,
) -> Compiled:
    """Build the change(s) for one field. Raises Unsupported or NothingToChange.

    Does not commit: the caller writes the credit that paid for it in the same
    transaction, so a result can never exist without its charge or vice versa."""
    if field in NOT_APPLICABLE:
        raise Unsupported(NOT_APPLICABLE[field])
    if field not in APPLICABLE_FIELDS:
        raise Unsupported(f"Signal has no automatic fix for {field.replace('_', ' ')}.")

    if field == "image_alt_text":
        return _compile_alt_text(session, page, html)

    before = read_current(html, field)

    if field == "canonical_tag":
        after, credits = _canonical(page, before), 0
    elif field == "robots_meta_tag":
        after, credits = _robots(before), 0
    else:
        after, credits = _generate(field, page, html), 1

    return Compiled(changes=[_upsert(session, page, field, "", before, after)], credits=credits)


def _generate(field: str, page: Page, html: str) -> str:
    try:
        if field == "title_tag":
            value = ai_suggestions.generate_title_tag(html, page.url, page.target_keyword)
        elif field == "meta_description":
            value = ai_suggestions.generate_meta_description(html, page.url, page.target_keyword)
        elif field == "structured_data":
            value = ai_suggestions.generate_structured_data(html, page.url, page.target_keyword)
        else:  # pragma: no cover - APPLICABLE_FIELDS and this branch list are checked above
            raise Unsupported(f"No generator for {field}.")
    except AIProviderError as exc:
        raise Unsupported(f"The AI provider could not produce a {field.replace('_', ' ')}: {exc}")

    if not value:
        raise NothingToChange(
            "The model did not return anything usable for this field. Nothing was charged; try again."
        )
    return value


def _compile_alt_text(session: Session, page: Page, html: str) -> Compiled:
    """One model call for every image missing alt text, one ProposedChange each.

    Charged as a single credit, matching POST /suggestions/alt-text: the cost is
    the call, and billing per image would make a page with eight images eight
    times as expensive to fix for no extra work."""
    try:
        suggestions = ai_suggestions.generate_alt_text_suggestions(html, page.url)
    except AIProviderError as exc:
        raise Unsupported(f"The AI provider could not produce alt text: {exc}")

    usable = [s for s in suggestions if s.get("src") and s.get("suggested_alt")]
    if not usable:
        raise NothingToChange("Every image on this page already has alt text.")

    changes = [
        _upsert(session, page, "image_alt_text", s["src"], current_alt(html, s["src"]), s["suggested_alt"])
        for s in usable
    ]
    return Compiled(changes=changes, credits=1)


def _upsert(
    session: Session,
    page: Page,
    field: str,
    subject: str,
    before: Optional[str],
    after: str,
) -> ProposedChange:
    """Replace an outstanding proposal for the same field, but never an applied
    one. Recompiling is "give me a better suggestion"; an applied row is the
    record of something that happened to a live site and is not a draft to
    overwrite."""
    existing = session.exec(
        select(ProposedChange).where(
            ProposedChange.page_id == page.id,
            ProposedChange.field == field,
            ProposedChange.subject == subject,
            ProposedChange.status.in_([ChangeStatus.proposed.value, ChangeStatus.failed.value]),
        )
    ).first()

    if existing is not None:
        existing.before = before
        existing.after = after
        existing.status = ChangeStatus.proposed.value
        existing.error = None
        existing.created_at = datetime.utcnow()
        session.add(existing)
        return existing

    row = ProposedChange(
        site_id=page.site_id,
        page_id=page.id,
        field=field,
        subject=subject,
        origin="audit_check",
        origin_ref=field,
        before=before,
        after=after,
    )
    session.add(row)
    return row


# --- staleness ---


def live_value(html: str, change: ProposedChange) -> Optional[str]:
    if change.field == "image_alt_text":
        return current_alt(html, change.subject)
    return read_current(html, change.field)


def is_stale(change: ProposedChange, html: str) -> bool:
    """True when the page no longer holds the value this change was built
    against - someone edited it after the change was compiled.

    Applying anyway would overwrite their edit with a suggestion written for the
    old page, so a stale change is refused and recompiled rather than forced. A
    change that has already been applied is compared against `after`, since that
    is what it put there."""
    expected = change.after if change.status == ChangeStatus.applied.value else change.before
    actual = live_value(html, change)
    return _norm(actual) != _norm(expected)


def _norm(value: Optional[str]) -> str:
    return " ".join((value or "").split())


def receipt_of(change: ProposedChange) -> Optional[dict]:
    if not change.receipt:
        return None
    try:
        return json.loads(change.receipt)
    except ValueError:
        return None


def value_warning(field: str, value: str) -> Optional[str]:
    """Whether this value would still not satisfy the check that asked for it.

    A model told to write 120-160 characters does not always write 120-160
    characters, and a change that leaves the check failing is a credit spent for
    nothing: the user applies it, the next audit still complains, and Signal
    looks like it does not know its own rules. Measured against the same
    constants audit_engine uses, so the two cannot drift.

    A warning, not a refusal - the value is usually still an improvement on
    nothing, and the user can see it and press "Rewrite it". Refusing would mean
    charging for the call and returning nothing."""
    length = len(value or "")
    if field == "title_tag" and not (audit_engine.TITLE_MIN_LEN <= length <= audit_engine.TITLE_MAX_LEN):
        return (
            f"This is {length} characters; the title check wants "
            f"{audit_engine.TITLE_MIN_LEN}-{audit_engine.TITLE_MAX_LEN}, so it will still be flagged."
        )
    if field == "meta_description" and not (
        audit_engine.META_DESC_MIN_LEN <= length <= audit_engine.META_DESC_MAX_LEN
    ):
        return (
            f"This is {length} characters; the meta description check wants "
            f"{audit_engine.META_DESC_MIN_LEN}-{audit_engine.META_DESC_MAX_LEN}, so it will still be flagged."
        )
    return None
