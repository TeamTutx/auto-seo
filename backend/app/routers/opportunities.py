from typing import List

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.deps import get_current_user
from app.models import User
from app.routers.sites import _get_owned_site
from app.schemas import Opportunity
from app.services.opportunities import get_site_opportunities

router = APIRouter(tags=["opportunities"])


@router.get("/sites/{site_id}/opportunities", response_model=List[Opportunity])
def list_opportunities(
    site_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    site = _get_owned_site(session, site_id, current_user)
    return get_site_opportunities(session, site.id)
