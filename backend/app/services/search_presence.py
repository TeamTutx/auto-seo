"""The two numbers the site page leads with: how visible a site is in Google,
and how visible it is in AI answers - plus the home page's search trend behind
them.

Everything here is derived from data Signal already has (Search Console and the
stored visibility checks). Nothing is fetched, so the site page stays fast and
costs nothing to open.
"""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, select

from app.models import KeywordIdea, Page, Site, VisibilityCheck
from app.services import visibility


def _pct(part: int, whole: int) -> Optional[int]:
    return round(part / whole * 100) if whole else None


# Search Console data is typically 2 days behind, sometimes 3.
REPORTING_LAG_DAYS = 3


def fill_gaps(rows: List[dict], days: int) -> List[dict]:
    """Search Console omits days with no impressions entirely. Plotting only the
    days that exist would compress gaps and make a quiet month look busy, so the
    missing ones are filled with zeros to keep the x-axis honest.

    The exception is the last few days. Search Console reports about two days
    behind, so those zeros mean "not counted yet", not "nobody came" - and
    drawing them plunges the line to the floor, which reads as traffic
    collapsing. They are trimmed instead. Only trailing zeros inside the known
    lag window go: a site that genuinely stopped getting impressions a week ago
    still sees that week, because that is real and worth seeing."""
    by_date = {row["date"]: row for row in rows}
    end = date.today()
    out = []
    for offset in range(days, -1, -1):
        day = (end - timedelta(days=offset)).isoformat()
        row = by_date.get(day)
        out.append(row or {"date": day, "clicks": 0, "impressions": 0, "position": None})

    trimmed = 0
    while out and trimmed < REPORTING_LAG_DAYS and out[-1]["impressions"] == 0:
        out.pop()
        trimmed += 1
    return out


def trailing_change(points: List[dict], key: str) -> Optional[int]:
    """Percent change of the last week against the week before it. None when
    there is nothing to compare against - a made-up 0% would read as "flat"
    rather than "we don't know yet"."""
    if len(points) < 14:
        return None
    recent = sum(p[key] or 0 for p in points[-7:])
    previous = sum(p[key] or 0 for p in points[-14:-7])
    if previous == 0:
        return 100 if recent else None
    return round((recent - previous) / previous * 100)


def home_page(session: Session, site: Site) -> Optional[Page]:
    """The page a site's trend is about. The home page is what "how is the site
    doing" means to most people; failing that, the first page tracked."""
    pages = session.exec(select(Page).where(Page.site_id == site.id).order_by(Page.id)).all()
    if not pages:
        return None
    roots = {f"https://{site.domain}", f"http://{site.domain}", f"https://www.{site.domain}"}
    for page in pages:
        if page.url.rstrip("/") in {r.rstrip("/") for r in roots}:
            return page
    return pages[0]


def visibility_scores(session: Session, site_id: int) -> Tuple[Dict, List[str]]:
    """How many targeted keywords the site is visible for, in Google and in AI
    answers. AI combines the Overview citation and the model mention: from the
    owner's side "am I in the AI answer" is one question, and splitting it into
    two small numbers makes it harder to read, not easier."""
    targeted = [
        idea.keyword
        for idea in session.exec(
            select(KeywordIdea).where(KeywordIdea.site_id == site_id, KeywordIdea.targeted == True)  # noqa: E712
        ).all()
    ]
    rows = session.exec(
        select(VisibilityCheck).where(VisibilityCheck.site_id == site_id).order_by(VisibilityCheck.id)
    ).all()
    newest: Dict[Tuple[str, str], VisibilityCheck] = {}
    for row in rows:
        newest[(row.keyword, row.engine)] = row

    google = ai_overview = chatgpt = ai_any = checked = 0
    positions: List[int] = []
    for keyword in targeted:
        engines = {e: newest.get((keyword, e)) for e in visibility.ENGINES}
        if not any(engines.values()):
            continue
        checked += 1
        if engines[visibility.GOOGLE] and engines[visibility.GOOGLE].present:
            google += 1
            if engines[visibility.GOOGLE].position:
                positions.append(engines[visibility.GOOGLE].position)
        overview_hit = bool(engines[visibility.AI_OVERVIEW] and engines[visibility.AI_OVERVIEW].present)
        chat_hit = bool(engines[visibility.CHATGPT] and engines[visibility.CHATGPT].present)
        ai_overview += overview_hit
        chatgpt += chat_hit
        ai_any += overview_hit or chat_hit

    last_checked: Optional[datetime] = max((r.checked_at for r in newest.values()), default=None)
    return {
        "targeted_keywords": len(targeted),
        "checked_keywords": checked,
        "google_visible": google,
        "google_score": _pct(google, checked),
        "best_position": min(positions) if positions else None,
        "ai_visible": ai_any,
        "ai_score": _pct(ai_any, checked),
        "ai_overview_cited": ai_overview,
        "chatgpt_mentions": chatgpt,
        "last_checked_at": last_checked,
    }, targeted
