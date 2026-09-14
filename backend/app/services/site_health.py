"""Site Health rollup (Signal roadmap Phase E - plan.md). Pure aggregation
over data already stored - no new tables, no external API calls.

Score trend reconstructs what the site's blended score (the same "average
of each page's latest audit" definition the site overview's gauge already
uses) would have read at every point in its audit history, not just right
now. Wins/losses are the biggest score and keyword-rank swings between each
page/keyword's two most recent checks.
"""
from typing import Dict, List, Tuple

from sqlmodel import Session, select

from app.models import Audit, KeywordRank, Page
from app.schemas import KeywordMovement, ScoreMovement, ScoreTrendPoint, SiteHealth
from app.services.opportunities import get_site_opportunities

TOP_N = 5
FOUND_OR_LOST_SENTINEL = 100  # synthetic delta for a keyword found/lost from nothing, for sorting only


def _score_trend(session: Session, page_ids: List[int]) -> List[ScoreTrendPoint]:
    if not page_ids:
        return []
    audits = session.exec(
        select(Audit).where(Audit.page_id.in_(page_ids)).order_by(Audit.created_at.asc())
    ).all()

    latest_by_page: Dict[int, int] = {}
    trend: List[ScoreTrendPoint] = []
    for audit in audits:
        if audit.score is None:
            continue
        latest_by_page[audit.page_id] = audit.score
        avg = sum(latest_by_page.values()) / len(latest_by_page)
        trend.append(ScoreTrendPoint(date=audit.created_at, score=round(avg, 1)))
    return trend


def _score_movements(session: Session, page_ids: List[int]) -> Tuple[List[ScoreMovement], List[ScoreMovement]]:
    movements: List[ScoreMovement] = []
    for page_id in page_ids:
        recent = session.exec(
            select(Audit).where(Audit.page_id == page_id).order_by(Audit.created_at.desc()).limit(2)
        ).all()
        if len(recent) < 2 or recent[0].score is None or recent[1].score is None:
            continue
        latest, previous = recent[0], recent[1]
        page = session.get(Page, page_id)
        movements.append(ScoreMovement(
            page_id=page_id,
            page_url=page.url,
            previous_score=previous.score,
            new_score=latest.score,
            delta=latest.score - previous.score,
        ))
    wins = sorted((m for m in movements if m.delta > 0), key=lambda m: m.delta, reverse=True)[:TOP_N]
    losses = sorted((m for m in movements if m.delta < 0), key=lambda m: m.delta)[:TOP_N]
    return wins, losses


def _keyword_movements(session: Session, page_ids: List[int]) -> Tuple[List[KeywordMovement], List[KeywordMovement]]:
    movements: List[KeywordMovement] = []
    for page_id in page_ids:
        ranks = session.exec(
            select(KeywordRank).where(KeywordRank.page_id == page_id).order_by(KeywordRank.checked_at.desc())
        ).all()
        by_keyword: Dict[str, List[KeywordRank]] = {}
        for rank in ranks:  # already newest first
            by_keyword.setdefault(rank.keyword, []).append(rank)

        page = session.get(Page, page_id)
        for keyword, history in by_keyword.items():
            if len(history) < 2:
                continue
            latest, previous = history[0], history[1]
            if latest.rank_position == previous.rank_position:
                continue

            if previous.rank_position is not None and latest.rank_position is not None:
                delta = previous.rank_position - latest.rank_position
            elif previous.rank_position is None and latest.rank_position is not None:
                delta = FOUND_OR_LOST_SENTINEL  # newly found - strong win
            else:
                delta = -FOUND_OR_LOST_SENTINEL  # newly lost - strong loss

            movements.append(KeywordMovement(
                page_id=page_id,
                page_url=page.url,
                keyword=keyword,
                previous_rank=previous.rank_position,
                new_rank=latest.rank_position,
                delta=delta,
            ))
    wins = sorted((m for m in movements if m.delta > 0), key=lambda m: m.delta, reverse=True)[:TOP_N]
    losses = sorted((m for m in movements if m.delta < 0), key=lambda m: m.delta)[:TOP_N]
    return wins, losses


def get_site_health(session: Session, site_id: int) -> SiteHealth:
    page_ids = session.exec(select(Page.id).where(Page.site_id == site_id)).all()
    score_wins, score_losses = _score_movements(session, page_ids)
    keyword_wins, keyword_losses = _keyword_movements(session, page_ids)
    return SiteHealth(
        score_trend=_score_trend(session, page_ids),
        score_wins=score_wins,
        score_losses=score_losses,
        keyword_wins=keyword_wins,
        keyword_losses=keyword_losses,
        top_opportunities=get_site_opportunities(session, site_id)[:TOP_N],
    )
