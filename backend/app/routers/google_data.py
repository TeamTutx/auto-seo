from typing import List, Tuple
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.database import get_session
from app.deps import get_current_user
from app.models import Page, Site, User
from app.routers.pages import get_owned_page
from app.routers.sites import _get_owned_site
from app.schemas import GAPageMetrics, GSCIndexStatus, GSCQueryRow
from app.services import ga, gsc
from app.services.ga import GAError
from app.services.google_connection import get_connection, get_valid_access_token
from app.services.google_oauth import GoogleOAuthError
from app.services.gsc import GSCError

router = APIRouter(tags=["google-data"])


def _ready_page(session: Session, page_id: int, current_user: User) -> Tuple[Page, Site, str]:
    page = get_owned_page(session, page_id, current_user)
    site = _get_owned_site(session, page.site_id, current_user)

    connection = get_connection(session, current_user.id)
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Connect Google in Settings first."
        )
    try:
        access_token = get_valid_access_token(session, connection)
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Google connection needs to be redone: {exc}")

    return page, site, access_token


@router.get("/pages/{page_id}/gsc/queries", response_model=List[GSCQueryRow])
def page_search_queries(
    page_id: int,
    days: int = Query(28, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    page, site, access_token = _ready_page(session, page_id, current_user)
    if not site.gsc_property:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This site isn't linked to a Search Console property yet - set one in Settings.",
        )
    try:
        rows = gsc.get_page_search_analytics(access_token, site.gsc_property, page.url, days=days)
    except GSCError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return [GSCQueryRow(**row) for row in rows]


@router.get("/pages/{page_id}/gsc/index-status", response_model=GSCIndexStatus)
def page_index_status(
    page_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    page, site, access_token = _ready_page(session, page_id, current_user)
    if not site.gsc_property:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This site isn't linked to a Search Console property yet - set one in Settings.",
        )
    try:
        result = gsc.inspect_url(access_token, site.gsc_property, page.url)
    except GSCError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return GSCIndexStatus(**result)


@router.get("/pages/{page_id}/ga/metrics", response_model=GAPageMetrics)
def page_ga_metrics(
    page_id: int,
    days: int = Query(28, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    page, site, access_token = _ready_page(session, page_id, current_user)
    if not site.ga_property_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This site isn't linked to an Analytics property yet - set one in Settings.",
        )
    path = urlparse(page.url).path or "/"
    try:
        metrics = ga.get_page_metrics(access_token, site.ga_property_id, path, days=days)
    except GAError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return GAPageMetrics(**metrics)
