from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.database import get_session
from app.deps import get_current_user
from app.models import Audit, User
from app.routers.pages import get_owned_page
from app.schemas import AuditRead
from app.services.audit_runner import audit_page

router = APIRouter(tags=["audits"])


@router.post("/pages/{page_id}/audits", response_model=AuditRead, status_code=status.HTTP_201_CREATED)
def run_audit(page_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Re-audit a page. Free, and deliberately unthrottled.

    There used to be a minimum gap between rescans of the same page - a day
    originally, as the free tier's upgrade nudge, later five minutes. Both were
    wrong for what this button is for: you edit your page, come back, and want
    to see whether the check cleared. Being told to wait is the one answer that
    is never useful, and it broke "Run full scan" outright, which audits every
    page in turn and so tripped the limit on its own previous run.

    What the limit was really protecting - not hammering someone's web server -
    is a fetch concern, so it lives with the fetch: one request per page, a
    timeout, and a bot user agent that identifies Signal (services/fetcher.py)."""
    page = get_owned_page(session, page_id, current_user)
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
