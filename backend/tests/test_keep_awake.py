"""The self-ping that keeps Render's free plan from sleeping the API.

No pytest-asyncio in this project, so the async pieces run under asyncio.run.
"""
import asyncio

import httpx

from app.config import settings
from app.services import keep_awake


def test_it_is_off_when_there_is_nothing_to_ping(monkeypatch):
    """Local dev and the test suite have no public URL, so nothing runs."""
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.setattr(settings, "keep_awake_url", "")

    assert keep_awake.target_url() is None


def test_on_render_it_pings_the_services_own_public_url(monkeypatch):
    """Render sets RENDER_EXTERNAL_URL on every web service, which is what makes
    this work in production with no configuration at all."""
    monkeypatch.setattr(settings, "keep_awake_url", "")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://signal-api-ecah.onrender.com/")

    assert keep_awake.target_url() == "https://signal-api-ecah.onrender.com/health"


def test_an_explicit_url_wins(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://signal-api-ecah.onrender.com")
    monkeypatch.setattr(settings, "keep_awake_url", "https://api.signal-seo.in")

    assert keep_awake.target_url() == "https://api.signal-seo.in/health"


def test_it_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://signal-api-ecah.onrender.com")
    monkeypatch.setattr(settings, "keep_awake", False)

    assert keep_awake.target_url() is None


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_a_ping_reports_a_healthy_answer():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"status": "ok"})

    async def run():
        async with _client(handler) as client:
            return await keep_awake.ping_once(client, "https://api.example/health")

    assert asyncio.run(run()) is True
    assert seen == ["https://api.example/health"]


def test_a_failed_ping_never_raises():
    """A missed ping is logged and the next one still has five minutes of slack.
    Raising would end the loop - and then the service goes to sleep for good."""
    def unreachable(request):
        raise httpx.ConnectError("no route to host")

    def unhealthy(request):
        return httpx.Response(503)

    async def run(handler):
        async with _client(handler) as client:
            return await keep_awake.ping_once(client, "https://api.example/health")

    assert asyncio.run(run(unreachable)) is False
    assert asyncio.run(run(unhealthy)) is False


def test_the_loop_keeps_pinging_until_cancelled(monkeypatch):
    pings = []

    async def fake_ping(client, url):
        pings.append(url)
        return True

    monkeypatch.setattr(keep_awake, "ping_once", fake_ping)

    async def run():
        task = asyncio.create_task(keep_awake.ping_forever("https://api.example/health", interval=0.01))
        await asyncio.sleep(0.1)
        task.cancel()

    asyncio.run(run())

    assert len(pings) >= 3  # it kept going rather than pinging once
    assert set(pings) == {"https://api.example/health"}


def test_the_interval_is_inside_renders_idle_window():
    """Render sleeps a free service after 15 idle minutes. The ping has to land
    well inside that, with room for one to fail."""
    assert keep_awake.INTERVAL_SECONDS <= 10 * 60
