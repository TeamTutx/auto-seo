from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.database import get_session
from app.deps import get_current_user
from app.models import PLAN_LIMITS, KeywordRank, User
from app.routers.pages import get_owned_page
from app.schemas import CompetitorResult, CompetitorsRequest, KeywordRankCreate, KeywordRankRead
from app.services.competitors import get_competitors
from app.services.credits import deduct_credit, require_credits
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
        max_keywords = PLAN_LIMITS[current_user.plan]["max_keywords_per_page"]
        if max_keywords is not None and len(existing) >= max_keywords:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    f"{current_user.plan} plan is limited to {max_keywords} tracked keyword(s) per page. "
                    "Upgrade to track more."
                ),
            )

    require_credits(current_user)
    result = check_keyword_rank(
        session, page, payload.keyword, payload.location_code, payload.language_code, payload.device
    )
    deduct_credit(session, current_user)
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
        deduct_credit(session, current_user)
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

    deduct_credit(session, current_user)
    return [
        CompetitorResult(position=c.position, title=c.title, domain=c.domain, url=c.url) for c in competitors
    ]
