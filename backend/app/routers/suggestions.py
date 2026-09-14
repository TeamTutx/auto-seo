from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.database import get_session
from app.deps import get_current_user
from app.models import User
from app.routers.pages import get_owned_page
from app.schemas import MetaDescriptionSuggestion, TitleTagSuggestion
from app.services.ai_providers import AIProviderError
from app.services.ai_suggestions import generate_meta_description, generate_title_tag
from app.services.credits import deduct_credit, require_credits
from app.services.fetcher import fetch_html

router = APIRouter(tags=["suggestions"])


def _fetch_and_suggest(
    page_id: int,
    current_user: User,
    session: Session,
    generate: Callable[[str, str, str], str],
) -> str:
    page = get_owned_page(session, page_id, current_user)
    require_credits(current_user)

    try:
        html = fetch_html(page.url)
    except Exception as exc:  # httpx raises several distinct error types here
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not fetch page: {exc}")

    try:
        suggestion = generate(html, page.url, page.target_keyword)
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    deduct_credit(session, current_user)
    return suggestion


@router.post("/pages/{page_id}/suggestions/meta-description", response_model=MetaDescriptionSuggestion)
def suggest_meta_description(
    page_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    suggestion = _fetch_and_suggest(page_id, current_user, session, generate_meta_description)
    return MetaDescriptionSuggestion(suggestion=suggestion)


@router.post("/pages/{page_id}/suggestions/title-tag", response_model=TitleTagSuggestion)
def suggest_title_tag(
    page_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    suggestion = _fetch_and_suggest(page_id, current_user, session, generate_title_tag)
    return TitleTagSuggestion(suggestion=suggestion)
