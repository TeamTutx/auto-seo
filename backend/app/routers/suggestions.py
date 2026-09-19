from typing import Callable, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.database import get_session
from app.deps import get_current_user
from app.models import Page, User
from app.routers.pages import get_owned_page
from app.schemas import (
    AltTextSuggestion,
    HeadingSuggestion,
    InternalLinkSuggestion,
    MetaDescriptionSuggestion,
    ReadabilitySuggestion,
    TitleTagSuggestion,
)
from app.services.ai_providers import AIProviderError
from app.services.ai_suggestions import (
    generate_alt_text_suggestions,
    generate_heading_suggestion,
    generate_internal_linking_suggestions,
    generate_meta_description,
    generate_readability_suggestion,
    generate_title_tag,
)
from app.services.credits import deduct_credit, require_credits
from app.services.fetcher import fetch_html

router = APIRouter(tags=["suggestions"])


def _fetch_and_suggest(
    page_id: int,
    current_user: User,
    session: Session,
    generate: Callable[[str, str, str], str],
    ref: str,
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

    deduct_credit(session, current_user, ref)
    return suggestion


@router.post("/pages/{page_id}/suggestions/meta-description", response_model=MetaDescriptionSuggestion)
def suggest_meta_description(
    page_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    suggestion = _fetch_and_suggest(page_id, current_user, session, generate_meta_description, "ai_meta_description")
    return MetaDescriptionSuggestion(suggestion=suggestion)


@router.post("/pages/{page_id}/suggestions/title-tag", response_model=TitleTagSuggestion)
def suggest_title_tag(
    page_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    suggestion = _fetch_and_suggest(page_id, current_user, session, generate_title_tag, "ai_title_tag")
    return TitleTagSuggestion(suggestion=suggestion)


@router.post("/pages/{page_id}/suggestions/heading", response_model=HeadingSuggestion)
def suggest_heading(
    page_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    suggestion = _fetch_and_suggest(page_id, current_user, session, generate_heading_suggestion, "ai_heading")
    return HeadingSuggestion(suggestion=suggestion)


@router.post("/pages/{page_id}/suggestions/readability", response_model=ReadabilitySuggestion)
def suggest_readability(
    page_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    suggestion = _fetch_and_suggest(page_id, current_user, session, generate_readability_suggestion, "ai_readability")
    return ReadabilitySuggestion(suggestion=suggestion)


@router.post("/pages/{page_id}/suggestions/alt-text", response_model=List[AltTextSuggestion])
def suggest_alt_text(
    page_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    page = get_owned_page(session, page_id, current_user)
    require_credits(current_user)

    try:
        html = fetch_html(page.url)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not fetch page: {exc}")

    try:
        suggestions = generate_alt_text_suggestions(html, page.url)
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    if not suggestions:
        return []

    deduct_credit(session, current_user, "ai_alt_text")
    return [AltTextSuggestion(**s) for s in suggestions]


@router.post("/pages/{page_id}/suggestions/internal-links", response_model=InternalLinkSuggestion)
def suggest_internal_links(
    page_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    page = get_owned_page(session, page_id, current_user)
    candidate_pages = session.exec(
        select(Page).where(Page.site_id == page.site_id, Page.id != page.id)
    ).all()
    if not candidate_pages:
        return InternalLinkSuggestion(
            suggestion="Add more pages to this site to get internal linking suggestions."
        )

    require_credits(current_user)

    try:
        html = fetch_html(page.url)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not fetch page: {exc}")

    try:
        suggestion = generate_internal_linking_suggestions(
            html, page.url, [(p.url, p.target_keyword) for p in candidate_pages]
        )
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    deduct_credit(session, current_user, "ai_internal_links")
    return InternalLinkSuggestion(suggestion=suggestion)
