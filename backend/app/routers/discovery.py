"""Crawl a site, discover keywords, and measure visibility.

All three kick off a background run (app/services/site_jobs.py) and return
immediately with a job the UI polls, because none of them finishes inside a
request. The POSTs are therefore "start this", not "here is the answer" — the
answer arrives in the GET endpoints as the job progresses.
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlmodel import Session, select

from app.database import get_session
from app.deps import get_current_user
from app.models import Audit, JobKind, KeywordIdea, Page, Site, SiteJob, User, VisibilityAdvice, VisibilityCheck
from app.routers.pages import get_owned_page
from app.routers.sites import _get_owned_site
from app.schemas import (
    IndexSummary,
    GeneratedResultRead,
    KeywordAddRequest,
    SearchPresence,
    TrendPoint,
    VisibilityActionRead,
    VisibilityAdviceRead,
    VisibilityAdviceRequest,
    KeywordIdeaRead,
    KeywordTargetRequest,
    PageRead,
    SiteJobRead,
    SiteJobs,
    VisibilityEngineRead,
    VisibilityKeywordRead,
    VisibilityReport,
)
from app.services import generated_results, gsc, index_status, search_presence, site_jobs, visibility, visibility_advice
from app.services.credits import deduct_credit, require_credits
from app.services import keyword_discovery
from app.services.fetcher import fetch_html
from app.services.gsc import GSCError

router = APIRouter(tags=["discovery"])
logger = logging.getLogger("signal.discovery")


def _advice_read(advice: Optional[VisibilityAdvice], engines: List[VisibilityEngineRead]) -> Optional[VisibilityAdviceRead]:
    if advice is None:
        return None
    try:
        actions = [VisibilityActionRead(**a) for a in json.loads(advice.actions)]
    except (ValueError, TypeError):
        actions = []
    # Advice about a search that has since been re-checked may describe a SERP
    # that no longer exists, which is worse than no advice unless it's labelled.
    newest_check = max((e.checked_at for e in engines), default=None)
    stale = bool(newest_check and advice.based_on_checked_at and newest_check > advice.based_on_checked_at)
    return VisibilityAdviceRead(
        diagnosis=advice.diagnosis, actions=actions, target_page_url=advice.target_page_url,
        created_at=advice.created_at, stale=stale,
    )


def _job_read(job: Optional[SiteJob]) -> Optional[SiteJobRead]:
    if job is None:
        return None
    # A job whose process died still says "running" in the database; report what
    # is actually true rather than leaving a spinner turning forever.
    status_value = "failed" if site_jobs.is_stale(job) else job.status
    error = job.error or ("Interrupted - the server restarted while this was running." if site_jobs.is_stale(job) else None)
    return SiteJobRead(
        id=job.id, kind=job.kind, status=status_value, progress=job.progress, total=job.total,
        message=job.message, error=error, credits_spent=job.credits_spent,
        created_at=job.created_at, finished_at=job.finished_at,
    )


def _start(background: BackgroundTasks, session: Session, site: Site, kind: JobKind, runner) -> SiteJobRead:
    try:
        job = site_jobs.claim(session, site.id, kind.value)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That's already running — give it a moment.",
        )
    background.add_task(site_jobs.start, job.id, runner)
    return _job_read(job)


@router.get("/sites/{site_id}/jobs", response_model=SiteJobs)
def site_jobs_status(
    site_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """The latest run of each kind. One poll covers the whole site page."""
    site = _get_owned_site(session, site_id, current_user)
    return SiteJobs(**{
        kind.value: _job_read(site_jobs.latest(session, site.id, kind.value))
        for kind in JobKind
    })


@router.get("/sites/{site_id}/presence", response_model=SearchPresence)
def site_presence(
    site_id: int,
    days: int = 28,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Google and AI visibility gauges, plus the home page's search trend. Reads
    stored data and (when connected) Search Console; never spends a credit, so
    the site page is free to open as often as the owner likes."""
    site = _get_owned_site(session, site_id, current_user)
    scores, _ = search_presence.visibility_scores(session, site.id)

    page = search_presence.home_page(session, site)
    google = site_jobs.google_access(session, site)
    unavailable = None
    rows: List[dict] = []

    if page is None:
        unavailable = "no_pages"
    elif google is None:
        unavailable = "no_property" if site.gsc_property else "no_google"
    else:
        try:
            rows = gsc.get_page_daily_metrics(*google, page.url, days=days)
        except GSCError:
            # An expired grant or a property the user only has partial access to
            # shouldn't blank the gauges, which don't need Google at all.
            unavailable = "no_google"

    points = search_presence.fill_gaps(rows, days) if rows else []
    if not points and unavailable is None:
        unavailable = "no_data"

    ranked = [p["position"] for p in points if p["position"]]
    return SearchPresence(
        **scores,
        trend_page_url=page.url if page else None,
        trend=[TrendPoint(**p) for p in points],
        clicks_total=sum(p["clicks"] for p in points),
        impressions_total=sum(p["impressions"] for p in points),
        clicks_change=search_presence.trailing_change(points, "clicks"),
        impressions_change=search_presence.trailing_change(points, "impressions"),
        average_position=round(sum(ranked) / len(ranked), 1) if ranked else None,
        trend_unavailable=unavailable,
    )


# --- crawl + index status ---

@router.post("/sites/{site_id}/crawl", response_model=SiteJobRead, status_code=status.HTTP_202_ACCEPTED)
def start_crawl(
    site_id: int,
    background: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Find the site's pages from its sitemap (or by following links) and, if
    Search Console is connected, check which are indexed. Costs no credits —
    Signal does the fetching itself and Google answers the index question free."""
    site = _get_owned_site(session, site_id, current_user)
    return _start(background, session, site, JobKind.crawl, site_jobs.run_crawl)


@router.get("/sites/{site_id}/index-summary", response_model=IndexSummary)
def index_summary(
    site_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    site = _get_owned_site(session, site_id, current_user)
    pages = session.exec(select(Page).where(Page.site_id == site.id)).all()
    latest_source = max(
        (p for p in pages if p.index_checked_at), key=lambda p: p.index_checked_at, default=None
    )
    return IndexSummary(
        total_pages=len(pages),
        indexed=sum(1 for p in pages if p.index_status == index_status.INDEXED),
        not_indexed=sum(1 for p in pages if p.index_status == index_status.NOT_INDEXED),
        unchecked=sum(1 for p in pages if p.index_status in (None, index_status.UNKNOWN)),
        source=latest_source.index_source if latest_source else None,
    )


@router.post("/pages/{page_id}/index-check", response_model=PageRead)
def check_one_page(
    page_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Check a single page's index status, paying a credit for a `site:` lookup
    when Search Console can't answer. Search Console is tried first and stays
    free, so this only charges when it actually has to."""
    page = get_owned_page(session, page_id, current_user)
    site = _get_owned_site(session, page.site_id, current_user)

    google = site_jobs.google_access(session, site)
    result = index_status.check_page(page.url, *(google or (None, None)))
    if result is None:
        require_credits(current_user)
        result = index_status.check_page_paid(page.url)
        deduct_credit(session, current_user, "index_check")

    index_status.apply_to_page(page, result)
    session.add(page)
    session.commit()
    session.refresh(page)
    return page


# --- keyword discovery ---

@router.post("/sites/{site_id}/keywords/discover", response_model=SiteJobRead, status_code=status.HTTP_202_ACCEPTED)
def start_keyword_discovery(
    site_id: int,
    background: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Suggest keywords from Search Console, the site's own home page, and
    Google's related searches. Up to 2 credits — Search Console is free, the
    other two are one each."""
    site = _get_owned_site(session, site_id, current_user)
    require_credits(current_user, needed=1)
    return _start(background, session, site, JobKind.keywords, site_jobs.run_keyword_discovery)


@router.get("/sites/{site_id}/keywords/ideas", response_model=List[KeywordIdeaRead])
def list_keyword_ideas(
    site_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Targeted ideas first, then measured Search Console ones, then guesses."""
    site = _get_owned_site(session, site_id, current_user)
    ideas = session.exec(select(KeywordIdea).where(KeywordIdea.site_id == site.id)).all()
    source_rank = {"gsc": 0, "serp": 1, "ai": 2}
    ideas.sort(key=lambda i: (
        not i.targeted,
        source_rank.get(i.source, 3),
        -(i.impressions or 0),
        i.keyword,
    ))
    return ideas


@router.post("/sites/{site_id}/keywords", response_model=KeywordIdeaRead, status_code=status.HTTP_201_CREATED)
def add_keyword(
    site_id: int,
    payload: KeywordAddRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Add a keyword by hand and target it straight away - the owner usually
    knows what they want to rank for without Signal suggesting it. Free: nothing
    is looked up until a visibility check actually runs.

    Adding one that already exists targets it rather than erroring, because
    that's what someone typing it again is asking for."""
    site = _get_owned_site(session, site_id, current_user)
    keyword = keyword_discovery.normalise(payload.keyword)
    if not keyword:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter a keyword.")

    existing = session.exec(
        select(KeywordIdea).where(KeywordIdea.site_id == site.id, KeywordIdea.keyword == keyword)
    ).first()
    if existing is not None:
        existing.targeted = True
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    idea = KeywordIdea(site_id=site.id, keyword=keyword, source="manual", targeted=True)
    session.add(idea)
    session.commit()
    session.refresh(idea)
    return idea


@router.post("/sites/{site_id}/keywords/target", response_model=List[KeywordIdeaRead])
def set_targeted(
    site_id: int,
    payload: KeywordTargetRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Mark ideas as ones the site wants to rank for. Targeted keywords are what
    a visibility run checks, so this is also how the owner controls that cost."""
    site = _get_owned_site(session, site_id, current_user)
    ideas = session.exec(
        select(KeywordIdea).where(KeywordIdea.site_id == site.id, KeywordIdea.id.in_(payload.ids))
    ).all()
    if len(ideas) != len(set(payload.ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Some of those keywords aren't on this site.")
    for idea in ideas:
        idea.targeted = payload.targeted
        session.add(idea)
    session.commit()
    return list_keyword_ideas(site_id, current_user, session)


@router.delete("/sites/{site_id}/keywords/ideas/{idea_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_idea(
    site_id: int,
    idea_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    site = _get_owned_site(session, site_id, current_user)
    idea = session.get(KeywordIdea, idea_id)
    if idea is None or idea.site_id != site.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keyword not found")
    session.delete(idea)
    session.commit()


# --- visibility ---

@router.post("/sites/{site_id}/visibility/check", response_model=SiteJobRead, status_code=status.HTTP_202_ACCEPTED)
def start_visibility_check(
    site_id: int,
    background: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Check every targeted keyword in Google and in an AI answer. Costs 2
    credits per keyword: one search (which covers both the organic ranking and
    the AI Overview) and one model question."""
    site = _get_owned_site(session, site_id, current_user)
    targeted = session.exec(
        select(KeywordIdea).where(KeywordIdea.site_id == site.id, KeywordIdea.targeted == True)  # noqa: E712
    ).all()
    if not targeted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pick the keywords you want to rank for first.",
        )
    # Enough for at least one keyword; the run stops cleanly when credits run
    # out rather than refusing to start on a balance that covers most of it.
    require_credits(current_user, needed=2)
    return _start(background, session, site, JobKind.visibility, site_jobs.run_visibility)


@router.get("/sites/{site_id}/visibility", response_model=VisibilityReport)
def visibility_report(
    site_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """The newest reading per keyword per engine. Older rows are kept in the
    table so a history view can be added without another migration."""
    site = _get_owned_site(session, site_id, current_user)
    targeted = [
        idea.keyword
        for idea in session.exec(
            select(KeywordIdea).where(KeywordIdea.site_id == site.id, KeywordIdea.targeted == True)  # noqa: E712
        ).all()
    ]
    rows = session.exec(
        select(VisibilityCheck).where(VisibilityCheck.site_id == site.id).order_by(VisibilityCheck.id)
    ).all()

    newest: Dict[tuple, VisibilityCheck] = {}
    for row in rows:
        newest[(row.keyword, row.engine)] = row  # ordered by id, so the last write wins

    advice_rows = session.exec(
        select(VisibilityAdvice).where(VisibilityAdvice.site_id == site.id).order_by(VisibilityAdvice.id)
    ).all()
    latest_advice = {a.keyword: a for a in advice_rows}  # ordered by id, so the last write wins

    keywords: List[VisibilityKeywordRead] = []
    checked_at: Optional[datetime] = None
    counts = {visibility.GOOGLE: 0, visibility.AI_OVERVIEW: 0, visibility.CHATGPT: 0}

    for keyword in targeted:
        engines = []
        for engine in visibility.ENGINES:
            row = newest.get((keyword, engine))
            if row is None:
                continue
            engines.append(VisibilityEngineRead(
                engine=row.engine, present=row.present, position=row.position,
                detail=row.detail, checked_at=row.checked_at,
            ))
            if row.present:
                counts[engine] = counts.get(engine, 0) + 1
            checked_at = max(checked_at, row.checked_at) if checked_at else row.checked_at
        keywords.append(VisibilityKeywordRead(
            keyword=keyword, engines=engines, advice=_advice_read(latest_advice.get(keyword), engines),
        ))

    return VisibilityReport(
        checked_at=checked_at,
        targeted_keywords=len(targeted),
        google_visible=counts[visibility.GOOGLE],
        ai_overview_cited=counts[visibility.AI_OVERVIEW],
        chatgpt_mentions=counts[visibility.CHATGPT],
        keywords=keywords,
    )


@router.post("/sites/{site_id}/visibility/suggest", response_model=VisibilityAdviceRead)
def suggest_for_keyword(
    site_id: int,
    payload: VisibilityAdviceRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Specific, evidence-backed advice for one keyword: what is beating this
    site in Google, what the AI answers cited instead, and what this site's own
    page is missing. One credit - the search that produced the evidence was
    already paid for by the visibility check."""
    site = _get_owned_site(session, site_id, current_user)
    keyword = payload.keyword.strip()

    rows = session.exec(
        select(VisibilityCheck)
        .where(VisibilityCheck.site_id == site.id, VisibilityCheck.keyword == keyword)
        .order_by(VisibilityCheck.id)
    ).all()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check this keyword's visibility first — the advice is built from what that check found.",
        )

    readings, contexts = {}, {}
    for row in rows:  # ordered by id, so the newest reading per engine wins
        readings[row.engine] = {"present": row.present, "position": row.position, "detail": row.detail or ""}
        if row.context:
            try:
                contexts[row.engine] = json.loads(row.context)
            except ValueError:
                pass
    if not contexts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This keyword was checked before Signal started recording who ranks for it. "
                "Run the check again and the advice will have something to work from."
            ),
        )

    pages = [
        {"url": page.url, "title": _latest_title(session, page.id)}
        for page in session.exec(select(Page).where(Page.site_id == site.id).order_by(Page.id)).all()
    ]
    candidate = visibility_advice.best_page(keyword, pages)
    content = None
    if candidate:
        try:
            content = _page_text(candidate["url"])
        except Exception as exc:  # a page we can't fetch shouldn't block the advice
            logger.info("advice: could not read %s: %s", candidate["url"], exc)

    require_credits(current_user)
    advice = visibility_advice.generate(
        keyword=keyword, domain=site.domain, readings=readings, contexts=contexts,
        page_url=candidate["url"] if candidate else None,
        page_title=candidate.get("title") if candidate else None,
        page_content=content, other_pages=pages,
    )
    if advice is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The model didn't return usable advice. Try again in a moment.",
        )
    deduct_credit(session, current_user, "visibility_advice")

    stored = VisibilityAdvice(
        site_id=site.id, keyword=keyword, diagnosis=advice.diagnosis,
        actions=json.dumps(advice.actions), target_page_url=advice.target_page_url,
        based_on_checked_at=max(r.checked_at for r in rows),
    )
    session.add(stored)
    session.commit()
    session.refresh(stored)
    return _advice_read(stored, [])


def _latest_title(session: Session, page_id: int) -> Optional[str]:
    audit = session.exec(
        select(Audit).where(Audit.page_id == page_id, Audit.extracted_title.is_not(None))
        .order_by(Audit.id.desc())
    ).first()
    return audit.extracted_title if audit else None


def _page_text(url: str) -> str:
    """The page's visible words, for the model to compare against what ranks.
    Free - Signal fetches it itself."""
    soup = BeautifulSoup(fetch_html(url), "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())


@router.get("/pages/{page_id}/generated", response_model=List[GeneratedResultRead])
def page_generated_results(
    page_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Everything a credit has already bought for this page - AI suggestions,
    competitor lookups, action plans. The page reads this on load so refreshing
    never costs the user the same answer twice. Free."""
    page = get_owned_page(session, page_id, current_user)
    rows = generated_results.for_page(session, page.id)
    return [
        GeneratedResultRead(
            kind=row.kind, subject=row.subject, payload=generated_results.decode(row), created_at=row.created_at,
        )
        for row in rows
        if generated_results.decode(row) is not None
    ]
