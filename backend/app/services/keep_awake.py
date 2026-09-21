"""Stop Render's free plan from putting the API to sleep.

A free Render web service spins down after 15 minutes without inbound traffic,
and the next visitor waits about a minute while it wakes - on "Continue with
Google", that means Render's loading page instead of Signal's.

This loop requests the service's *own public URL* every ten minutes. The request
leaves the instance and comes back in through Render's proxy, which is where
idle time is measured, so it counts as traffic. Pinging localhost would not.

Why not the GitHub Actions workflow (.github/workflows/keep-backend-alive.yml),
which tries the same thing from outside? GitHub treats scheduled workflows as
best effort: over four days in September 2026 it ran a `*/10` schedule 29
times instead of ~560, with a median gap of 173 minutes. Every gap was longer
than the 15 minutes that matters. That workflow stays, as a backstop that wakes
the service if this loop ever dies with it asleep.

The hour budget: Render grants 750 free instance-hours per workspace per month
and an always-on service uses at most 744 (a 31-day month). That only fits if
nothing else in the workspace draws on the pool, so the older free services in
it were suspended when this went in. Resuming one of them without moving this
service to a paid instance risks exhausting the pool - at which point Render
suspends *every* free service, this one included, until the 1st.
"""
import asyncio
import logging
import os
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger("signal.keep_awake")

# Render sleeps a service after 15 idle minutes. Ten leaves room for one slow or
# failed ping without the service dropping off.
INTERVAL_SECONDS = 10 * 60
TIMEOUT_SECONDS = 30


def target_url() -> Optional[str]:
    """The URL to ping, or None to not run at all.

    `KEEP_AWAKE_URL` wins if set. Otherwise `RENDER_EXTERNAL_URL`, which Render
    sets on every web service - so this is on in production with no config, and
    off in local dev and the test suite, where neither exists. `KEEP_AWAKE=false`
    turns it off everywhere (e.g. once the service is on a paid instance that
    doesn't sleep, though leaving it on there is harmless)."""
    if not settings.keep_awake:
        return None
    base = (settings.keep_awake_url or os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    return f"{base}/health" if base else None


async def ping_once(client: httpx.AsyncClient, url: str) -> bool:
    """One ping. Never raises: a missed ping is logged and the next one in ten
    minutes still has five minutes of slack before Render would sleep."""
    try:
        response = await client.get(url)
    except httpx.HTTPError as exc:
        logger.warning("keep-awake ping to %s failed: %s", url, exc)
        return False
    if response.status_code != 200:
        logger.warning("keep-awake ping to %s returned %s", url, response.status_code)
        return False
    return True


async def ping_forever(url: str, interval: float = INTERVAL_SECONDS) -> None:
    """Run for the life of the process. Sleeps first: a service that has just
    started has just had traffic (the deploy's health check, or the request that
    woke it), so the idle clock is already reset."""
    logger.info("keep-awake: pinging %s every %s seconds", url, int(interval))
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        while True:
            await asyncio.sleep(interval)
            await ping_once(client, url)
