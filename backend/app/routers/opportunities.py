from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.database import get_session
from app.deps import get_current_user
from app.models import OpportunityType, User
from app.routers.pages import get_owned_page
from app.routers.sites import _get_owned_site
from app.schemas import ApplyFixRequest, AppliedFixRead, Opportunity
from app.services.applied_fixes import mark_applied
from app.services.opportunities import get_site_opportunities

router = APIRouter(tags=["opportunities"])


@router.get("/sites/{site_id}/opportunities", response_model=List[Opportunity])
def list_opportunities(
    site_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    site = _get_owned_site(session, site_id, current_user)
    return get_site_opportunities(session, site.id)


@router.post("/pages/{page_id}/opportunities/apply", response_model=AppliedFixRead, status_code=status.HTTP_201_CREATED)
def apply_opportunity(
    page_id: int,
    payload: ApplyFixRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """User says they've applied a suggested fix themselves (Signal has no
    write access to their site). Records a baseline so the next audit/rank
    check for this page can confirm whether it actually worked."""
    page = get_owned_page(session, page_id, current_user)

    if payload.type in (OpportunityType.audit_fail, OpportunityType.audit_warning) and not payload.check_type:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="check_type is required for this opportunity type")
    if payload.type != OpportunityType.audit_fail and payload.type != OpportunityType.audit_warning and not payload.keyword:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="keyword is required for this opportunity type")

    fix = mark_applied(session, page, payload.type, payload.check_type, payload.keyword)
    return AppliedFixRead(
        id=fix.id,
        page_id=fix.page_id,
        type=fix.opportunity_type,
        check_type=fix.check_type,
        keyword=fix.keyword,
        applied_at=fix.applied_at,
        resolved=fix.resolved,
        resolved_at=fix.resolved_at,
    )
