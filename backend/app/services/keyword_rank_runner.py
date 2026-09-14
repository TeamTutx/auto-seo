from fastapi import HTTPException, status
from sqlmodel import Session

from app.models import KeywordRank, Page, Site
from app.services.applied_fixes import verify_applied_fixes_for_keyword
from app.services.rank_providers import RankProviderError, get_rank_provider


def check_keyword_rank(
    session: Session,
    page: Page,
    keyword: str,
    location_code: int = 2356,  # India - see app/models.py KeywordRank.location_code
    language_code: str = "en",
    device: str = "desktop",
) -> KeywordRank:
    # Match against page.url rather than site.domain: page.url is a real,
    # validated URL (it has to be - the audit engine already fetches it),
    # while site.domain is free text with no format enforcement and can
    # drift from the actual site (e.g. a typo like "zepto" instead of
    # "zepto.com" silently breaks every rank check for that site).
    provider = get_rank_provider()
    try:
        rank_position = provider.fetch_rank(keyword, page.url, location_code, language_code, device)
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

    site = session.get(Site, page.site_id)
    if site is not None:
        verify_applied_fixes_for_keyword(session, site.user_id, page, keyword_rank)

    return keyword_rank
