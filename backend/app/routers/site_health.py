from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.deps import get_current_user
from app.models import User
from app.routers.sites import _get_owned_site
from app.schemas import SiteHealth
from app.services.site_health import get_site_health

router = APIRouter(tags=["site-health"])


@router.get("/sites/{site_id}/health", response_model=SiteHealth)
def site_health(
    site_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    site = _get_owned_site(session, site_id, current_user)
    return get_site_health(session, site.id)
