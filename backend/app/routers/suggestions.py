from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.database import get_session
from app.deps import get_current_user
from app.models import User
from app.routers.pages import get_owned_page
from app.schemas import MetaDescriptionSuggestion
from app.services.ai_providers import AIProviderError
from app.services.ai_suggestions import generate_meta_description
from app.services.credits import deduct_credit, require_credits
from app.services.fetcher import fetch_html

router = APIRouter(tags=["suggestions"])


@router.post("/pages/{page_id}/suggestions/meta-description", response_model=MetaDescriptionSuggestion)
def suggest_meta_description(
    page_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    page = get_owned_page(session, page_id, current_user)
    require_credits(current_user)

    try:
        html = fetch_html(page.url)
    except Exception as exc:  # httpx raises several distinct error types here
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not fetch page: {exc}")

    try:
        suggestion = generate_meta_description(html, page.url, page.target_keyword)
    except AIProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    deduct_credit(session, current_user)
    return MetaDescriptionSuggestion(suggestion=suggestion)
