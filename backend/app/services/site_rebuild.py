"""Ask the marketing site to rebuild itself.

The landing page renders `GET /pricing` into static HTML at build time, so a
pack the owner creates or reprices in /admin/pricing only reaches visitors on
the next build. This pokes Render's deploy hook to start one.

It lives on the API rather than in the frontend because a deploy hook URL is a
credential - anyone holding it can spend the workspace's build minutes - and
anything the browser can send is public. The admin's request reaches the API
already; the API holds the secret.

Best-effort by design: pricing is correct in the database either way, and a
failed rebuild must never fail the edit that triggered it. With
RENDER_DEPLOY_HOOK_URL unset (local dev, self-hosting, any other host) this is a
no-op, which is also what keeps the test suite from calling out.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger("signal.rebuild")

TIMEOUT_SECONDS = 10


def request_rebuild(reason: str) -> bool:
    """Start a rebuild of the public site. Returns whether one was triggered -
    for logging and tests, not for the caller to act on."""
    hook = (settings.render_deploy_hook_url or "").strip()
    if not hook:
        logger.debug("rebuild skipped (%s): no RENDER_DEPLOY_HOOK_URL set", reason)
        return False
    try:
        response = httpx.post(hook, timeout=TIMEOUT_SECONDS)
        if response.status_code >= 400:
            logger.warning("rebuild request (%s) returned %s", reason, response.status_code)
            return False
    except httpx.HTTPError as exc:
        logger.warning("rebuild request (%s) failed: %s", reason, exc)
        return False
    logger.info("rebuild requested (%s)", reason)
    return True
