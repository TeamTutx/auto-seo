"""Inbound payment webhooks. No login - the request is authenticated solely by
its signature, verified against the raw body before anything is parsed."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session

from app.config import settings
from app.database import get_session
from app.services import dodo
from app.services.dodo_webhooks import handle_event

logger = logging.getLogger("signal.billing")
router = APIRouter(tags=["webhooks"])


async def _raw_body(request: Request) -> bytes:
    return await request.body()


@router.post("/webhooks/dodo")
def dodo_webhook(request: Request, body: bytes = Depends(_raw_body), session: Session = Depends(get_session)):
    if not settings.dodo_webhook_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing isn't configured.")
    try:
        event = dodo.verify_webhook(body, request.headers, settings.dodo_webhook_key)
    except dodo.WebhookVerificationError as exc:
        # 400, not 401: a bad signature will never become valid on a retry.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid webhook: {exc}")

    try:
        result = handle_event(session, event)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Dodo webhook %s failed", event.get("type"))
        # A 5xx makes Dodo retry (up to 8 times) - right for a transient DB error.
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Webhook processing failed")
    logger.info("Dodo webhook %s -> %s", event.get("type"), result)
    return {"received": True, "result": result}
