from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.database import get_session
from app.deps import get_current_user
from app.models import ACCOUNT_LIMITS, KeywordRank, User
from app.routers.pages import get_owned_page
from app.schemas import (
    CompetitorResult,
    CompetitorsRequest,
    KeywordOpportunity,
    KeywordRankCreate,
    KeywordRankRead,
    RankingActionPlan,
)
from app.services.ai_providers import AIProviderError
from app.services.competitors import get_competitors
from app.services import generated_results
from app.services.credits import deduct_credit, require_credits
from app.services.fetcher import fetch_html
from app.services.keyword_opportunities import generate_keyword_opportunities, generate_ranking_action_plan
from app.services.keyword_rank_runner import check_keyword_rank
from app.services.rank_providers import RankProviderError

router = APIRouter(tags=["keywords"])


def _all_ranks(session: Session, page_id: int) -> List[KeywordRank]:
    return session.exec(
        select(KeywordRank).where(KeywordRank.page_id == page_id).order_by(KeywordRank.checked_at.desc())
    ).all()


def _latest_per_keyword(ranks: List[KeywordRank]) -> List[KeywordRank]:
    seen = set()
    latest = []
    for rank in ranks:  # already ordered newest first
        if rank.keyword not in seen:
            seen.add(rank.keyword)
            latest.append(rank)
    return latest


@router.post("/pages/{page_id}/keywords", response_model=KeywordRankRead, status_code=status.HTTP_201_CREATED)
def add_keyword(
    page_id: int,
    payload: KeywordRankCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    page = get_owned_page(session, page_id, current_user)

    existing = _latest_per_keyword(_all_ranks(session, page.id))
    is_new_keyword = payload.keyword not in {r.keyword for r in existing}

    if is_new_keyword:
        max_keywords = ACCOUNT_LIMITS["max_keywords_per_page"]
        if max_keywords is not None and len(existing) >= max_keywords:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    f"A page can track {max_keywords} keywords. "
                    "Remove one you no longer need, or email support."
                ),
            )

    require_credits(current_user)
    result = check_keyword_rank(
        session, page, payload.keyword, payload.location_code, payload.language_code, payload.device
    )
    deduct_credit(session, current_user, "keyword_check")
    return result


@router.get("/pages/{page_id}/keywords", response_model=List[KeywordRankRead])
def list_tracked_keywords(
    page_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    page = get_owned_page(session, page_id, current_user)
    return _latest_per_keyword(_all_ranks(session, page.id))


@router.get("/pages/{page_id}/keywords/history", response_model=List[KeywordRankRead])
def keyword_history(
    page_id: int,
    keyword: str = Query(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    page = get_owned_page(session, page_id, current_user)
    return [r for r in _all_ranks(session, page.id) if r.keyword == keyword][::-1]


@router.delete("/pages/{page_id}/keywords", status_code=status.HTTP_204_NO_CONTENT)
def delete_keyword(
    page_id: int,
    keyword: str = Query(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Stop tracking a keyword entirely - removes every historical rank row
    for it on this page, not just the latest."""
    page = get_owned_page(session, page_id, current_user)
    ranks = session.exec(
        select(KeywordRank).where(KeywordRank.page_id == page.id, KeywordRank.keyword == keyword)
    ).all()
    if not ranks:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keyword not tracked")
    for rank in ranks:
        session.delete(rank)
    session.commit()


@router.post("/pages/{page_id}/keywords/recheck", response_model=List[KeywordRankRead])
def recheck_keywords(
    page_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    page = get_owned_page(session, page_id, current_user)
    existing = _latest_per_keyword(_all_ranks(session, page.id))
    if not existing:
        return []

    require_credits(current_user, needed=len(existing))

    results = []
    for rank in existing:
        try:
            result = check_keyword_rank(
                session, page, rank.keyword, rank.location_code, rank.language_code, rank.device
            )
        except HTTPException:
            continue
        deduct_credit(session, current_user, "keyword_recheck")
        results.append(result)
    return results


@router.post("/pages/{page_id}/keywords/competitors", response_model=List[CompetitorResult])
def keyword_competitors(
    page_id: int,
    payload: CompetitorsRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    page = get_owned_page(session, page_id, current_user)
    require_credits(current_user)

    try:
        competitors = get_competitors(
            payload.keyword, page.url, payload.location_code, payload.language_code, payload.device
        )
    except RankProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    deduct_credit(session, current_user, "competitor_lookup")
    generated_results.store(
        session, page.id, generated_results.COMPETITORS,
        [{"position": c.position, "title": c.title, "domain": c.domain, "url": c.url} for c in competitors],
        subject=payload.keyword,
    )
    session.commit()
    return [
        CompetitorResult(position=c.position, title=c.title, domain=c.domain, url=c.url) for c in competitors
    ]


@router.post("/pages/{page_id}/keywords/opportunities", response_model=List[KeywordOpportunity])
def keyword_opportunities(
    page_id: int,
    payload: CompetitorsRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """AI-suggested related keywords, based on who's outranking this page for
    `payload.keyword` (Signal roadmap Phase C - plan.md). Costs 2 credits:
    one for the competitor SERP lookup, one for the AI call."""
    page = get_owned_page(session, page_id, current_user)
    require_credits(current_user, needed=2)

    try:
        competitors = get_competitors(
            payload.keyword, page.url, payload.location_code, payload.language_code, payload.device
        )
    except RankProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    deduct_credit(session, current_user, "keyword_opportunities_serp")

    try:
        html = fetch_html(page.url)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not fetch page: {exc}")

    try:
        opportunities = generate_keyword_opportunities(html, page.url, payload.keyword, competitors)
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    deduct_credit(session, current_user, "keyword_opportunities_ai")
    generated_results.store(
        session, page.id, generated_results.KEYWORD_OPPORTUNITIES, opportunities, subject=payload.keyword,
    )
    session.commit()
    return [KeywordOpportunity(**o) for o in opportunities]


@router.post("/pages/{page_id}/keywords/action-plan", response_model=RankingActionPlan)
def keyword_action_plan(
    page_id: int,
    payload: CompetitorsRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """AI action plan for getting `payload.keyword` to rank at all, or better,
    on this page - for when a tracked keyword has no rank yet (or a poor
    one). Costs 2 credits like keyword opportunities: one for the competitor
    SERP lookup, one for the AI call."""
    page = get_owned_page(session, page_id, current_user)
    require_credits(current_user, needed=2)

    try:
        competitors = get_competitors(
            payload.keyword, page.url, payload.location_code, payload.language_code, payload.device
        )
    except RankProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    deduct_credit(session, current_user, "action_plan_serp")

    try:
        html = fetch_html(page.url)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not fetch page: {exc}")

    try:
        plan = generate_ranking_action_plan(html, page.url, payload.keyword, competitors)
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    deduct_credit(session, current_user, "action_plan_ai")
    generated_results.store(
        session, page.id, generated_results.ACTION_PLAN, {"plan": plan}, subject=payload.keyword,
    )
    session.commit()
    return RankingActionPlan(plan=plan)
