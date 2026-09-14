"""Track/verify loop for AI-suggested fixes (Signal roadmap Phase D -
plan.md). Signal has no write access to a user's actual site - a user
applies a suggestion themselves (copies it into their own CMS/code) and
tells us via mark_applied(). The baseline captured there lets the next
audit or rank check - which already runs on every manual rescan/recheck,
not just Pro/Agency's scheduled ones - confirm whether the issue actually
cleared, via verify_applied_fixes_for_audit/_for_keyword below.
"""
from datetime import datetime
from typing import List, Optional

from sqlmodel import Session, select

from app.models import Alert, AlertType, AppliedFix, Audit, Check, CheckStatus, KeywordRank, OpportunityType, Page

LOW_RANK_THRESHOLD = 10  # keep in sync with app/services/opportunities.py

_AUDIT_TYPES = (OpportunityType.audit_fail, OpportunityType.audit_warning)
_KEYWORD_TYPES = (OpportunityType.keyword_not_found, OpportunityType.keyword_low_rank, OpportunityType.keyword_rank_drop)


def mark_applied(
    session: Session,
    page: Page,
    opportunity_type: OpportunityType,
    check_type: Optional[str],
    keyword: Optional[str],
) -> AppliedFix:
    baseline_score = None
    baseline_rank = None

    if opportunity_type in _AUDIT_TYPES:
        latest_audit = session.exec(
            select(Audit).where(Audit.page_id == page.id).order_by(Audit.created_at.desc())
        ).first()
        baseline_score = latest_audit.score if latest_audit else None
    else:
        latest_rank = session.exec(
            select(KeywordRank)
            .where(KeywordRank.page_id == page.id, KeywordRank.keyword == keyword)
            .order_by(KeywordRank.checked_at.desc())
        ).first()
        baseline_rank = latest_rank.rank_position if latest_rank else None

    fix = AppliedFix(
        page_id=page.id,
        opportunity_type=opportunity_type,
        check_type=check_type,
        keyword=keyword,
        baseline_score=baseline_score,
        baseline_rank=baseline_rank,
    )
    session.add(fix)
    session.commit()
    session.refresh(fix)
    return fix


def pending_fixes(session: Session, page_id: int) -> List[AppliedFix]:
    return session.exec(
        select(AppliedFix).where(AppliedFix.page_id == page_id, AppliedFix.resolved.is_(False))
    ).all()


def _humanize(check_type: str) -> str:
    return check_type.replace("_", " ").title()


def verify_applied_fixes_for_audit(session: Session, user_id: int, page: Page, audit: Audit) -> List[Alert]:
    pending = session.exec(
        select(AppliedFix).where(
            AppliedFix.page_id == page.id,
            AppliedFix.resolved.is_(False),
            AppliedFix.opportunity_type.in_(_AUDIT_TYPES),
        )
    ).all()
    if not pending:
        return []

    checks_by_type = {c.check_type: c for c in session.exec(select(Check).where(Check.audit_id == audit.id)).all()}

    alerts: List[Alert] = []
    for fix in pending:
        check = checks_by_type.get(fix.check_type) if fix.check_type else None
        if check is None or check.status != CheckStatus.pass_:
            continue
        fix.resolved = True
        fix.resolved_at = datetime.utcnow()
        session.add(fix)
        alerts.append(Alert(
            user_id=user_id,
            page_id=page.id,
            alert_type=AlertType.fix_verified,
            message=f'{page.url}: "{_humanize(fix.check_type)}" fix verified - now passing.',
        ))

    if alerts:
        session.add_all(alerts)
        session.commit()
    return alerts


def verify_applied_fixes_for_keyword(
    session: Session, user_id: int, page: Page, keyword_rank: KeywordRank
) -> List[Alert]:
    pending = session.exec(
        select(AppliedFix).where(
            AppliedFix.page_id == page.id,
            AppliedFix.keyword == keyword_rank.keyword,
            AppliedFix.resolved.is_(False),
            AppliedFix.opportunity_type.in_(_KEYWORD_TYPES),
        )
    ).all()
    if not pending:
        return []

    new_position = keyword_rank.rank_position
    alerts: List[Alert] = []
    for fix in pending:
        if new_position is None:
            continue  # still not found - nothing to verify yet
        improved = fix.baseline_rank is None or new_position <= fix.baseline_rank
        if fix.opportunity_type == OpportunityType.keyword_low_rank:
            improved = improved and new_position <= LOW_RANK_THRESHOLD
        if not improved:
            continue

        fix.resolved = True
        fix.resolved_at = datetime.utcnow()
        session.add(fix)
        was = "not found" if fix.baseline_rank is None else f"#{fix.baseline_rank}"
        alerts.append(Alert(
            user_id=user_id,
            page_id=page.id,
            alert_type=AlertType.fix_verified,
            message=f'{page.url}: "{fix.keyword}" now ranks #{new_position} (was {was}).',
        ))

    if alerts:
        session.add_all(alerts)
        session.commit()
    return alerts
