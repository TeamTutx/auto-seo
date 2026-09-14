import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.database import get_session
from app.deps import get_current_user
from app.models import PLAN_LIMITS, Site, User, VerificationMethod
from app.schemas import SiteCreate, SiteRead, SiteUpdate, SiteVerificationResult, SiteVerifyRequest
from app.services.cascade_delete import delete_site
from app.services.site_verification import verify_dns_txt, verify_file_upload, verify_meta_tag

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


@router.patch("/{site_id}", response_model=SiteRead)
def update_site(
    site_id: int,
    payload: SiteUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    site = _get_owned_site(session, site_id, current_user)
    if payload.domain is not None and payload.domain != site.domain:
        site.domain = payload.domain
        # A domain change invalidates whatever was verified before.
        site.verified = False
        site.verification_method = None
    if payload.gsc_property is not None:
        site.gsc_property = payload.gsc_property or None
    if payload.ga_property_id is not None:
        site.ga_property_id = payload.ga_property_id or None
    session.add(site)
    session.commit()
    session.refresh(site)
    return site


@router.post("/{site_id}/verify", response_model=SiteVerificationResult)
def verify_site(
    site_id: int,
    payload: SiteVerifyRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    site = _get_owned_site(session, site_id, current_user)

    if payload.method == VerificationMethod.dns_txt:
        verified, message = verify_dns_txt(site.domain, site.verification_token)
    elif payload.method == VerificationMethod.meta_tag:
        verified, message = verify_meta_tag(site.domain, site.verification_token)
    else:
        verified, message = verify_file_upload(site.domain, site.verification_token)

    if verified:
        site.verified = True
        site.verification_method = payload.method
        session.add(site)
        session.commit()

    return SiteVerificationResult(verified=verified, message=message)


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_site(
    site_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    site = _get_owned_site(session, site_id, current_user)
    delete_site(session, site.id)


def _get_owned_site(session: Session, site_id: int, current_user: User) -> Site:
    site = session.get(Site, site_id)
    if site is None or site.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return site
