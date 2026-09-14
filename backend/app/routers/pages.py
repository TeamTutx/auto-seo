from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.database import get_session
from app.deps import get_current_user
from app.models import PLAN_LIMITS, Page, User
from app.routers.sites import _get_owned_site
from app.schemas import PageCreate, PageRead, PageUpdate
from app.services.cascade_delete import delete_page

router = APIRouter(tags=["pages"])


@router.post("/sites/{site_id}/pages", response_model=PageRead, status_code=status.HTTP_201_CREATED)
def create_page(
    site_id: int,
    payload: PageCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    site = _get_owned_site(session, site_id, current_user)

    existing_count = len(session.exec(select(Page).where(Page.site_id == site.id)).all())
    max_pages = PLAN_LIMITS[current_user.plan]["max_pages_per_site"]
    if max_pages is not None and existing_count >= max_pages:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"{current_user.plan} plan is limited to {max_pages} page(s) per site. Upgrade to add more.",
        )

    page = Page(site_id=site.id, url=payload.url, target_keyword=payload.target_keyword)
    session.add(page)
    session.commit()
    session.refresh(page)
    return page


@router.get("/sites/{site_id}/pages", response_model=list)
def list_pages(
    site_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    site = _get_owned_site(session, site_id, current_user)
    return session.exec(select(Page).where(Page.site_id == site.id)).all()


def get_owned_page(session: Session, page_id: int, current_user: User) -> Page:
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    _get_owned_site(session, page.site_id, current_user)  # raises if not owned
    return page


@router.get("/pages/{page_id}", response_model=PageRead)
def get_page(page_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return get_owned_page(session, page_id, current_user)


@router.patch("/pages/{page_id}", response_model=PageRead)
def update_page(
    page_id: int,
    payload: PageUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    page = get_owned_page(session, page_id, current_user)
    if payload.url is not None:
        page.url = payload.url
    if payload.target_keyword is not None:
        page.target_keyword = payload.target_keyword or None
    session.add(page)
    session.commit()
    session.refresh(page)
    return page


@router.delete("/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_page(
    page_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    page = get_owned_page(session, page_id, current_user)
    delete_page(session, page.id)
