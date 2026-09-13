import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.database import get_session
from app.deps import get_current_user
from app.models import PLAN_LIMITS, Site, User
from app.schemas import SiteCreate, SiteRead

router = APIRouter(prefix="/sites", tags=["sites"])


@router.post("", response_model=SiteRead, status_code=status.HTTP_201_CREATED)
def create_site(
    payload: SiteCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    existing_count = len(session.exec(select(Site).where(Site.user_id == current_user.id)).all())
    max_sites = PLAN_LIMITS[current_user.plan]["max_sites"]
    if max_sites is not None and existing_count >= max_sites:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"{current_user.plan} plan is limited to {max_sites} site(s). Upgrade to add more.",
        )

    site = Site(
        user_id=current_user.id,
        domain=payload.domain,
        verification_token=f"signal-verify-{secrets.token_hex(16)}",
    )
    session.add(site)
    session.commit()
    session.refresh(site)
    return site


@router.get("", response_model=list)
def list_sites(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return session.exec(select(Site).where(Site.user_id == current_user.id)).all()


@router.get("/{site_id}", response_model=SiteRead)
def get_site(site_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    site = _get_owned_site(session, site_id, current_user)
    return site


def _get_owned_site(session: Session, site_id: int, current_user: User) -> Site:
    site = session.get(Site, site_id)
    if site is None or site.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return site
