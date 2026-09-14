from typing import Dict, List

from sqlmodel import Session, select

from app.models import Audit, Check, CheckStatus, KeywordRank, Page
from app.schemas import Opportunity, OpportunitySeverity, OpportunityType

LOW_RANK_THRESHOLD = 10  # outside the first page of results
RANK_DROP_THRESHOLD = 3  # positions worse than the previous check to count as a regression

_SEVERITY_ORDER = {OpportunitySeverity.high: 0, OpportunitySeverity.medium: 1, OpportunitySeverity.low: 2}


def _humanize(check_type: str) -> str:
    return check_type.replace("_", " ").title()


def _audit_opportunities(session: Session, page: Page) -> List[Opportunity]:
    latest_audit = session.exec(
        select(Audit).where(Audit.page_id == page.id).order_by(Audit.created_at.desc())
    ).first()
    if latest_audit is None:
        return []

    checks = session.exec(select(Check).where(Check.audit_id == latest_audit.id)).all()
    opportunities = []
    for check in checks:
        if check.status == CheckStatus.fail:
            opportunities.append(
                Opportunity(
                    type=OpportunityType.audit_fail,
                    severity=OpportunitySeverity.high,
                    page_id=page.id,
                    page_url=page.url,
                    title=f"{_humanize(check.check_type)} needs fixing",
                    detail=check.message,
                    suggested_fix=check.suggested_fix,
                    check_type=check.check_type,
                )
            )
        elif check.status == CheckStatus.warning:
            opportunities.append(
                Opportunity(
                    type=OpportunityType.audit_warning,
                    severity=OpportunitySeverity.medium,
                    page_id=page.id,
                    page_url=page.url,
                    title=f"{_humanize(check.check_type)} could be better",
                    detail=check.message,
                    suggested_fix=check.suggested_fix,
                    check_type=check.check_type,
                )
            )
    return opportunities


def _ranks_by_keyword(session: Session, page_id: int) -> Dict[str, List[KeywordRank]]:
    ranks = session.exec(
        select(KeywordRank).where(KeywordRank.page_id == page_id).order_by(KeywordRank.checked_at.desc())
    ).all()
    by_keyword: Dict[str, List[KeywordRank]] = {}
    for rank in ranks:  # already newest first
        by_keyword.setdefault(rank.keyword, []).append(rank)
    return by_keyword


def _keyword_opportunities(session: Session, page: Page) -> List[Opportunity]:
    opportunities = []
    for history in _ranks_by_keyword(session, page.id).values():
        latest = history[0]
        previous = history[1] if len(history) > 1 else None

        if latest.rank_position is None:
            opportunities.append(
                Opportunity(
                    type=OpportunityType.keyword_not_found,
                    severity=OpportunitySeverity.high,
                    page_id=page.id,
                    page_url=page.url,
                    title=f'Not ranking for "{latest.keyword}"',
                    detail=f'This page didn\'t show up in the tracked results for "{latest.keyword}".',
                    keyword=latest.keyword,
                )
            )
        elif latest.rank_position > LOW_RANK_THRESHOLD:
            opportunities.append(
                Opportunity(
                    type=OpportunityType.keyword_low_rank,
                    severity=OpportunitySeverity.medium,
                    page_id=page.id,
                    page_url=page.url,
                    title=f'Ranking #{latest.rank_position} for "{latest.keyword}"',
                    detail="Outside the first page of results - there's room to climb.",
                    keyword=latest.keyword,
                )
            )

        if (
            previous is not None
            and previous.rank_position is not None
            and latest.rank_position is not None
            and latest.rank_position - previous.rank_position >= RANK_DROP_THRESHOLD
        ):
            opportunities.append(
                Opportunity(
                    type=OpportunityType.keyword_rank_drop,
                    severity=OpportunitySeverity.high,
                    page_id=page.id,
                    page_url=page.url,
                    title=f'Rank dropped for "{latest.keyword}"',
                    detail=f"Fell from #{previous.rank_position} to #{latest.rank_position} since the last check.",
                    keyword=latest.keyword,
                )
            )
    return opportunities


def get_site_opportunities(session: Session, site_id: int) -> List[Opportunity]:
    pages = session.exec(select(Page).where(Page.site_id == site_id)).all()
    opportunities: List[Opportunity] = []
    for page in pages:
        opportunities.extend(_audit_opportunities(session, page))
        opportunities.extend(_keyword_opportunities(session, page))
    return sorted(opportunities, key=lambda o: _SEVERITY_ORDER[o.severity])
