from fastapi import HTTPException, status
from sqlmodel import Session

from app.models import KeywordRank, Page
from app.services.rank_providers import RankProviderError, get_rank_provider


def check_keyword_rank(
    session: Session,
    page: Page,
    keyword: str,
    location_code: int = 2840,
    language_code: str = "en",
    device: str = "desktop",
) -> KeywordRank:
    site = page.site
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found for page")

    provider = get_rank_provider()
    try:
        rank_position = provider.fetch_rank(keyword, site.domain, location_code, language_code, device)
    except RankProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    keyword_rank = KeywordRank(
        page_id=page.id,
        keyword=keyword,
        rank_position=rank_position,
        provider=provider.name,
        location_code=location_code,
        language_code=language_code,
        device=device,
    )
    session.add(keyword_rank)
    session.commit()
    session.refresh(keyword_rank)
    return keyword_rank
