"""Crawl a site, discover keywords, and measure visibility.

All three kick off a background run (app/services/site_jobs.py) and return
immediately with a job the UI polls, because none of them finishes inside a
request. The POSTs are therefore "start this", not "here is the answer" — the
answer arrives in the GET endpoints as the job progresses.
"""
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlmodel import Session, select

from app.database import get_session
from app.deps import get_current_user
from app.models import JobKind, KeywordIdea, Page, Site, SiteJob, User, VisibilityCheck
from app.routers.pages import get_owned_page
from app.routers.sites import _get_owned_site
from app.schemas import (
    IndexSummary,
    KeywordIdeaRead,
    KeywordTargetRequest,
    PageRead,
    SiteJobRead,
    SiteJobs,
    VisibilityEngineRead,
    VisibilityKeywordRead,
    VisibilityReport,
)
from app.services import index_status, site_jobs, visibility
from app.services.credits import deduct_credit, require_credits

router = APIRouter(tags=["discovery"])


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
        keywords.append(VisibilityKeywordRead(keyword=keyword, engines=engines))

    return VisibilityReport(
        checked_at=checked_at,
        targeted_keywords=len(targeted),
        google_visible=counts[visibility.GOOGLE],
        ai_overview_cited=counts[visibility.AI_OVERVIEW],
        chatgpt_mentions=counts[visibility.CHATGPT],
        keywords=keywords,
    )
