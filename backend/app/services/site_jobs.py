"""Background runs for the three slow features: crawling a site, discovering
keywords, and checking visibility.

These take minutes. They run in the API process via FastAPI's BackgroundTasks
rather than a worker queue, because Render's free tier has no worker and a
monthly bill for one isn't worth it yet (see plan.md Phase J). That choice has
consequences this module has to handle:

- **Its own database session.** The request's session is closed the moment the
  response goes out, so every job opens a fresh one.
- **Commit as you go.** Progress is only visible to the polling UI once it is
  committed, so each unit of work commits rather than batching to the end.
- **Jobs can die mid-run.** A deploy or restart kills the process and leaves a
  row saying "running" forever. `claim` treats a job that hasn't moved in
  STALE_AFTER as dead, so the owner can just start another one.
- **Credits are spent one at a time**, after each unit succeeds, so a job that
  dies halfway has charged only for what it actually did.

If a worker is ever provisioned, only `start` needs to change.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Callable, List, Optional

from bs4 import BeautifulSoup
from sqlmodel import Session, select

from app.database import engine
from app.models import (
    ACCOUNT_LIMITS,
    CreditReason,
    JobStatus,
    KeywordIdea,
    Page,
    Site,
    SiteJob,
    User,
    VisibilityCheck,
)
from app.services import gsc, index_status, keyword_discovery, visibility
from app.services.credits import InsufficientCredits, apply_credit_delta
from app.services.crawler import discover
from app.services.fetcher import fetch_html
from app.services.google_connection import get_connection, get_valid_access_token
from app.services.google_oauth import GoogleOAuthError
from app.services.gsc import GSCError

logger = logging.getLogger("signal.jobs")


def session_factory() -> Session:
    """A job's own database session. The request's session is closed the moment
    the response goes out, so a job cannot borrow it. Indirected through a
    function so tests can point jobs at their own engine - without this, a job
    started in a test would quietly write to the real database."""
    return Session(engine)

# A job whose heartbeat is older than this is assumed dead with the process
# that was running it.
STALE_AFTER = timedelta(minutes=15)


class OutOfCredits(Exception):
    """Stop the run; what's already been done stays done."""


# --- job lifecycle ---

def latest(session: Session, site_id: int, kind: str) -> Optional[SiteJob]:
    return session.exec(
        select(SiteJob).where(SiteJob.site_id == site_id, SiteJob.kind == kind).order_by(SiteJob.id.desc())
    ).first()


def is_stale(job: SiteJob) -> bool:
    heartbeat = job.started_at or job.created_at
    return job.status == JobStatus.running.value and datetime.utcnow() - heartbeat > STALE_AFTER


def claim(session: Session, site_id: int, kind: str) -> SiteJob:
    """Start a job, unless one of this kind is genuinely still running."""
    existing = latest(session, site_id, kind)
    if existing and existing.status in (JobStatus.queued.value, JobStatus.running.value):
        if not is_stale(existing):
            raise RuntimeError("already_running")
        existing.status = JobStatus.failed.value
        existing.error = "Interrupted - the server restarted while this was running."
        existing.finished_at = datetime.utcnow()
        session.add(existing)

    job = SiteJob(site_id=site_id, kind=kind, status=JobStatus.queued.value)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _progress(session: Session, job: SiteJob, *, message: Optional[str] = None,
              progress: Optional[int] = None, total: Optional[int] = None) -> None:
    if message is not None:
        job.message = message
    if progress is not None:
        job.progress = progress
    if total is not None:
        job.total = total
    job.started_at = job.started_at or datetime.utcnow()
    session.add(job)
    session.commit()


def _spend(session: Session, job: SiteJob, user_id: int, ref: str) -> None:
    try:
        apply_credit_delta(session, user_id, -1, CreditReason.usage, ref=ref)
    except InsufficientCredits:
        session.rollback()
        raise OutOfCredits()
    job.credits_spent += 1
    session.add(job)


def start(job_id: int, runner: Callable[[Session, SiteJob], None]) -> None:
    """Entry point handed to BackgroundTasks. Owns the session and the job's
    final state, so a runner only has to do the work and raise on failure."""
    with session_factory() as session:
        job = session.get(SiteJob, job_id)
        if job is None:
            return
        job.status = JobStatus.running.value
        job.started_at = datetime.utcnow()
        session.add(job)
        session.commit()

        try:
            runner(session, job)
            job.status = JobStatus.done.value
        except OutOfCredits:
            job.status = JobStatus.done.value
            job.message = (job.message or "") + " — stopped early: out of credits."
        except Exception as exc:  # a background job must never take the process down
            logger.exception("job %s (%s) failed", job_id, job.kind)
            session.rollback()
            job = session.get(SiteJob, job_id)
            job.status = JobStatus.failed.value
            job.error = str(exc)[:500]
        job.finished_at = datetime.utcnow()
        session.add(job)
        session.commit()


# --- shared helpers ---

def google_access(session: Session, site: Site) -> Optional[tuple]:
    """(access_token, property_url) when this site can use Search Console, else
    None. Both halves are needed: a connected account is useless here until the
    owner has told us which property belongs to this site."""
    if not site.gsc_property:
        return None
    connection = get_connection(session, site.user_id)
    if connection is None:
        return None
    try:
        return get_valid_access_token(session, connection), site.gsc_property
    except GoogleOAuthError:
        return None


# --- crawl ---

def run_crawl(session: Session, job: SiteJob) -> None:
    site = session.get(Site, job.site_id)
    limit = ACCOUNT_LIMITS["max_pages_per_site"]
    _progress(session, job, message=f"Looking for pages on {site.domain}…", total=limit)

    found = discover(site.domain, limit)
    existing = {p.url.rstrip("/") for p in session.exec(select(Page).where(Page.site_id == site.id)).all()}
    room = limit - len(existing)

    added = 0
    for item in found:
        if room <= 0:
            break
        if item.url.rstrip("/") in existing:
            continue
        session.add(Page(site_id=site.id, url=item.url, discovered_via=item.via))
        existing.add(item.url.rstrip("/"))
        added += 1
        room -= 1
    session.commit()

    pages = session.exec(select(Page).where(Page.site_id == site.id).order_by(Page.id)).all()
    _progress(
        session, job,
        message=f"Found {len(found)} page(s), {added} new. Checking which are indexed…",
        progress=0, total=len(pages),
    )

    google = google_access(session, site)
    if google is None:
        _progress(
            session, job, progress=len(pages),
            message=(
                f"Found {len(found)} page(s), {added} new. Connect Google Search Console in Settings "
                "to see which are indexed for free."
            ),
        )
        return

    access_token, property_url = google
    checked = unindexed = 0
    for i, page in enumerate(pages, start=1):
        result = index_status.check_page(page.url, access_token, property_url)
        if result:
            index_status.apply_to_page(page, result)
            session.add(page)
            checked += 1
            if result["status"] != index_status.INDEXED:
                unindexed += 1
        if i % 5 == 0 or i == len(pages):
            _progress(session, job, progress=i)

    summary = f"Found {len(found)} page(s), {added} new. Checked {checked} against Search Console"
    summary += f" — {unindexed} not indexed." if unindexed else " — all indexed."
    _progress(session, job, progress=len(pages), message=summary)


# --- keyword discovery ---

def run_keyword_discovery(session: Session, job: SiteJob) -> None:
    site = session.get(Site, job.site_id)
    _progress(session, job, message="Reading Search Console…", total=3, progress=0)

    gsc_ideas = []
    google = google_access(session, site)
    if google:
        try:
            rows = gsc.get_site_search_analytics(*google)
            gsc_ideas = keyword_discovery.from_search_console(rows)
        except GSCError as exc:
            logger.info("keyword discovery: Search Console unavailable: %s", exc)

    _progress(session, job, progress=1, message="Reading your pages…")
    ai_ideas = []
    page = _seed_page(session, site)
    if page is not None:
        try:
            html = fetch_html(page.url)
            _spend(session, job, site.user_id, "keyword_ideas_ai")
            session.commit()
            ai_ideas = keyword_discovery.from_page_content(_visible_text(html), site.domain)
        except OutOfCredits:
            raise
        except Exception as exc:
            logger.info("keyword discovery: could not read %s: %s", page.url, exc)

    _progress(session, job, progress=2, message="Asking Google for related searches…")
    related = []
    seed = _seed_keyword(gsc_ideas, ai_ideas, site)
    if seed:
        try:
            _spend(session, job, site.user_id, "keyword_ideas_related")
            session.commit()
            related = keyword_discovery.from_related_searches(seed)
        except OutOfCredits:
            pass  # everything found so far is still worth saving

    ideas = keyword_discovery.merge(gsc_ideas, ai_ideas, related)
    added = _save_ideas(session, site.id, ideas)
    _progress(
        session, job, progress=3,
        message=f"{len(ideas)} keyword idea(s), {added} new. Pick the ones you want to target.",
    )


def _seed_page(session: Session, site: Site) -> Optional[Page]:
    """The home page by default - it is the page that says what the whole site
    is about, which is what keyword ideas should come from."""
    pages = session.exec(select(Page).where(Page.site_id == site.id).order_by(Page.id)).all()
    if not pages:
        return None
    root = f"https://{site.domain.rstrip('/')}"
    for page in pages:
        if page.url.rstrip("/") in (root, f"http://{site.domain}"):
            return page
    return pages[0]


def _seed_keyword(gsc_ideas: List, ai_ideas: List, site: Site) -> Optional[str]:
    if gsc_ideas:
        return gsc_ideas[0].keyword
    if ai_ideas:
        return ai_ideas[0].keyword
    return None


def _visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())


def _save_ideas(session: Session, site_id: int, ideas: List) -> int:
    """Upsert by (site, keyword). An existing idea keeps whether it is targeted
    but takes any newly measured Search Console numbers."""
    existing = {
        idea.keyword: idea
        for idea in session.exec(select(KeywordIdea).where(KeywordIdea.site_id == site_id)).all()
    }
    added = 0
    for idea in ideas:
        current = existing.get(idea.keyword)
        if current is None:
            session.add(KeywordIdea(
                site_id=site_id, keyword=idea.keyword, source=idea.source, rationale=idea.rationale,
                impressions=idea.impressions, clicks=idea.clicks, position=idea.position,
            ))
            added += 1
        elif idea.source == "gsc":
            current.impressions = idea.impressions
            current.clicks = idea.clicks
            current.position = idea.position
            current.source = "gsc"
            session.add(current)
    session.commit()
    return added


# --- visibility ---

def run_visibility(session: Session, job: SiteJob) -> None:
    site = session.get(Site, job.site_id)
    keywords = [
        idea.keyword
        for idea in session.exec(
            select(KeywordIdea).where(KeywordIdea.site_id == site.id, KeywordIdea.targeted == True)  # noqa: E712
        ).all()
    ]
    if not keywords:
        _progress(session, job, message="No targeted keywords yet — pick some first.", total=0, progress=0)
        return

    _progress(session, job, message=f"Checking {len(keywords)} keyword(s)…", total=len(keywords), progress=0)
    seen = 0
    for i, keyword in enumerate(keywords, start=1):
        _spend(session, job, site.user_id, "visibility_google")
        session.commit()
        results = visibility.check_google(keyword, site.domain)

        try:
            _spend(session, job, site.user_id, "visibility_ai")
            session.commit()
            results.append(visibility.check_chatgpt(keyword, site.domain))
        except OutOfCredits:
            pass  # the Google half of this keyword is already paid for and worth keeping

        for result in results:
            session.add(VisibilityCheck(
                site_id=site.id, keyword=keyword, engine=result.engine,
                present=result.present, position=result.position, detail=result.detail,
                context=json.dumps(result.context) if result.context else None,
            ))
        if any(r.present for r in results):
            seen += 1
        _progress(session, job, progress=i)

    _progress(session, job, progress=len(keywords),
              message=f"Checked {len(keywords)} keyword(s) — visible for {seen}.")
