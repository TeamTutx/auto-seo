from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import exists
from sqlmodel import Session, select

from app.database import get_session
from app.deps import get_current_user
from app.models import Audit, Check, PlanTier, User
from app.routers.pages import get_owned_page
from app.schemas import AuditRead
from app.services.audit_runner import audit_page

router = APIRouter(tags=["audits"])

RESCAN_THROTTLE = timedelta(days=1)


@router.post("/pages/{page_id}/audits", response_model=AuditRead, status_code=status.HTTP_201_CREATED)
def run_audit(page_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    page = get_owned_page(session, page_id, current_user)

    if current_user.plan == PlanTier.free:
        # Only audits that actually stored checks count toward the throttle - an
        # audit row with no checks (left behind by a failed check insert before
        # audit_page became atomic) gave the user nothing, so it shouldn't cost
        # them their daily rescan.
        last_audit = session.exec(
            select(Audit)
            .where(Audit.page_id == page.id, exists().where(Check.audit_id == Audit.id))
            .order_by(Audit.created_at.desc())
        ).first()
        if last_audit and datetime.utcnow() - last_audit.created_at < RESCAN_THROTTLE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Free plan allows one rescan per day per page. Upgrade for unlimited rescans.",
            )

    return audit_page(session, page.id)


@router.get("/pages/{page_id}/audits", response_model=list)
def list_audits(page_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    page = get_owned_page(session, page_id, current_user)
    return session.exec(
        select(Audit).where(Audit.page_id == page.id).order_by(Audit.created_at.desc())
    ).all()


@router.get("/audits/{audit_id}", response_model=AuditRead)
def get_audit(audit_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    audit = session.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    get_owned_page(session, audit.page_id, current_user)  # raises if not owned
    return audit
