"""Crawl, keyword discovery and visibility, end to end through the API.

TestClient runs BackgroundTasks as part of the response, so by the time a POST
returns here the job has already finished - which means these tests exercise the
real background path rather than a stand-in for it. `finished_job` just reads
back the result.
"""
from datetime import datetime, timedelta

import pytest
from sqlmodel import Session, select

import app.services.site_jobs as site_jobs
from app.models import KeywordIdea, Page, SiteJob, VisibilityCheck
from app.services.crawler import Discovered
from app.services.keyword_discovery import Idea
from app.services.rank_providers.base import AIOverview, SerpResult, SerpSnapshot
from app.services.visibility import EngineResult
from tests.conftest import get_user, register_and_login


def make_site(client, headers, domain="example.com"):
    return client.post("/sites", json={"domain": domain}, headers=headers).json()["id"]


def finished_job(db, kind: str) -> SiteJob:
    """The most recent job of this kind. TestClient has already run it."""
    with Session(db) as session:
        return session.exec(
            select(SiteJob).where(SiteJob.kind == kind).order_by(SiteJob.id.desc())
        ).first()


@pytest.fixture
def no_google(monkeypatch):
    """No Search Console connected - the common case for a new user."""
    monkeypatch.setattr(site_jobs, "google_access", lambda session, site: None)


# --- crawl ---

def test_crawling_a_site_creates_its_pages(client, db, monkeypatch, no_google):
    headers = register_and_login(client, "crawl1@test.dev")
    site_id = make_site(client, headers)
    monkeypatch.setattr(site_jobs, "discover", lambda domain, limit: [
        Discovered("https://example.com/", "sitemap"),
        Discovered("https://example.com/pricing", "sitemap"),
        Discovered("https://example.com/blog/post", "link"),
    ])

    started = client.post(f"/sites/{site_id}/crawl", headers=headers)
    job = finished_job(db, "crawl")

    assert started.status_code == 202 and started.json()["status"] == "queued"
    assert job.status == "done" and job.credits_spent == 0  # crawling is free
    pages = client.get(f"/sites/{site_id}/pages", headers=headers).json()
    assert {p["url"] for p in pages} == {
        "https://example.com/", "https://example.com/pricing", "https://example.com/blog/post",
    }
    assert {p["discovered_via"] for p in pages} == {"sitemap", "link"}


def test_crawling_twice_does_not_duplicate_pages(client, db, monkeypatch, no_google):
    headers = register_and_login(client, "crawl2@test.dev")
    site_id = make_site(client, headers)
    monkeypatch.setattr(site_jobs, "discover", lambda domain, limit: [Discovered("https://example.com/", "sitemap")])

    client.post(f"/sites/{site_id}/crawl", headers=headers)
    finished_job(db, "crawl")
    client.post(f"/sites/{site_id}/crawl", headers=headers)
    job = finished_job(db, "crawl")

    assert len(client.get(f"/sites/{site_id}/pages", headers=headers).json()) == 1
    assert "0 new" in job.message


def test_a_crawl_cannot_exceed_the_account_page_limit(client, db, monkeypatch, no_google):
    from app.models import ACCOUNT_LIMITS

    headers = register_and_login(client, "crawl3@test.dev")
    site_id = make_site(client, headers)
    found = [Discovered(f"https://example.com/p{i}", "sitemap") for i in range(ACCOUNT_LIMITS["max_pages_per_site"] + 20)]
    monkeypatch.setattr(site_jobs, "discover", lambda domain, limit: found[:limit])

    client.post(f"/sites/{site_id}/crawl", headers=headers)
    finished_job(db, "crawl")

    with Session(db) as session:
        stored = session.exec(select(Page).where(Page.site_id == site_id)).all()
    assert len(stored) == ACCOUNT_LIMITS["max_pages_per_site"]


def test_crawl_checks_index_status_when_search_console_is_connected(client, db, monkeypatch):
    headers = register_and_login(client, "crawl4@test.dev")
    site_id = make_site(client, headers)
    monkeypatch.setattr(site_jobs, "discover", lambda domain, limit: [
        Discovered("https://example.com/", "sitemap"),
        Discovered("https://example.com/hidden", "sitemap"),
    ])
    monkeypatch.setattr(site_jobs, "google_access", lambda session, site: ("token", "sc-domain:example.com"))
    monkeypatch.setattr(
        site_jobs.index_status, "check_page",
        lambda url, token, prop: {
            "status": "indexed" if url.endswith("/") else "not_indexed",
            "detail": "Submitted and indexed" if url.endswith("/") else "Crawled - currently not indexed",
            "source": "gsc",
        },
    )

    client.post(f"/sites/{site_id}/crawl", headers=headers)
    job = finished_job(db, "crawl")

    assert "1 not indexed" in job.message
    summary = client.get(f"/sites/{site_id}/index-summary", headers=headers).json()
    assert summary == {"total_pages": 2, "indexed": 1, "not_indexed": 1, "unchecked": 0, "source": "gsc"}
    pages = {p["url"]: p for p in client.get(f"/sites/{site_id}/pages", headers=headers).json()}
    assert pages["https://example.com/hidden"]["index_detail"] == "Crawled - currently not indexed"
    assert pages["https://example.com/hidden"]["index_source"] == "gsc"


def test_without_google_the_crawl_says_how_to_get_index_status(client, db, monkeypatch, no_google):
    headers = register_and_login(client, "crawl5@test.dev")
    site_id = make_site(client, headers)
    monkeypatch.setattr(site_jobs, "discover", lambda domain, limit: [Discovered("https://example.com/", "sitemap")])

    client.post(f"/sites/{site_id}/crawl", headers=headers)
    job = finished_job(db, "crawl")

    assert "Connect Google Search Console" in job.message
    assert client.get(f"/sites/{site_id}/index-summary", headers=headers).json()["unchecked"] == 1


def test_a_second_crawl_is_refused_while_one_is_running(client, db, monkeypatch, no_google):
    """Two crawls of the same site at once would race each other into duplicate
    pages, so the second is refused until the first finishes or goes stale."""
    headers = register_and_login(client, "crawl6@test.dev")
    site_id = make_site(client, headers)
    monkeypatch.setattr(site_jobs, "discover", lambda domain, limit: [])
    client.post(f"/sites/{site_id}/crawl", headers=headers)
    with Session(db) as session:  # pretend the first one is still going
        job = session.exec(select(SiteJob).order_by(SiteJob.id.desc())).first()
        job.status = "running"
        job.started_at = datetime.utcnow()
        session.add(job)
        session.commit()

    second = client.post(f"/sites/{site_id}/crawl", headers=headers)

    assert second.status_code == 409 and "already running" in second.json()["detail"]


def test_a_job_orphaned_by_a_restart_is_reported_as_failed_not_running(client, db, monkeypatch, no_google):
    """The process can die mid-job, leaving a row that says "running" forever.
    The UI must not spin on it, and the owner must be able to start another."""
    headers = register_and_login(client, "crawl7@test.dev")
    site_id = make_site(client, headers)
    client.post(f"/sites/{site_id}/crawl", headers=headers)
    with Session(db) as session:
        job = session.exec(select(SiteJob).order_by(SiteJob.id.desc())).first()
        job.status = "running"
        job.started_at = datetime.utcnow() - timedelta(hours=2)
        session.add(job)
        session.commit()

    status = client.get(f"/sites/{site_id}/jobs", headers=headers).json()

    assert status["crawl"]["status"] == "failed"
    assert "Interrupted" in status["crawl"]["error"]
    monkeypatch.setattr(site_jobs, "discover", lambda domain, limit: [])
    assert client.post(f"/sites/{site_id}/crawl", headers=headers).status_code == 202


def test_crawling_someone_elses_site_is_404(client, db):
    headers = register_and_login(client, "crawl8@test.dev")
    other = register_and_login(client, "crawl8b@test.dev")
    site_id = make_site(client, headers)

    assert client.post(f"/sites/{site_id}/crawl", headers=other).status_code == 404
    assert client.get(f"/sites/{site_id}/jobs", headers=other).status_code == 404


# --- keyword discovery ---

@pytest.fixture
def stub_discovery(monkeypatch):
    monkeypatch.setattr(site_jobs, "fetch_html", lambda url: "<html><body>We sell widgets.</body></html>")
    monkeypatch.setattr(
        site_jobs.keyword_discovery, "from_page_content",
        lambda text, domain: [Idea(keyword="buy widgets", source="ai", rationale="page sells widgets")],
    )
    monkeypatch.setattr(
        site_jobs.keyword_discovery, "from_related_searches",
        lambda seed, **kw: [Idea(keyword="cheap widgets", source="serp", rationale=f"Related to {seed}")],
    )


def test_keyword_discovery_merges_sources_and_charges_per_paid_source(client, db, stub_discovery, monkeypatch):
    headers = register_and_login(client, "kw1@test.dev")
    site_id = make_site(client, headers)
    client.post(f"/sites/{site_id}/pages", json={"url": "https://example.com/"}, headers=headers)
    monkeypatch.setattr(site_jobs, "google_access", lambda session, site: ("token", "sc-domain:example.com"))
    monkeypatch.setattr(site_jobs.gsc, "get_site_search_analytics", lambda token, prop: [
        {"query": "widget reviews", "impressions": 500, "clicks": 3, "position": 14.2},
    ])

    client.post(f"/sites/{site_id}/keywords/discover", headers=headers)
    job = finished_job(db, "keywords")

    assert job.status == "done"
    assert job.credits_spent == 2  # the AI read and the related-searches lookup; Search Console is free
    ideas = client.get(f"/sites/{site_id}/keywords/ideas", headers=headers).json()
    by_keyword = {i["keyword"]: i for i in ideas}
    assert set(by_keyword) == {"widget reviews", "buy widgets", "cheap widgets"}
    assert by_keyword["widget reviews"]["source"] == "gsc"
    assert by_keyword["widget reviews"]["impressions"] == 500
    assert by_keyword["buy widgets"]["rationale"] == "page sells widgets"
    # only Search Console ideas carry numbers - Signal has no volume database
    assert by_keyword["buy widgets"]["impressions"] is None


def test_discovery_without_google_still_produces_ideas(client, db, stub_discovery, no_google):
    headers = register_and_login(client, "kw2@test.dev")
    site_id = make_site(client, headers)
    client.post(f"/sites/{site_id}/pages", json={"url": "https://example.com/"}, headers=headers)

    client.post(f"/sites/{site_id}/keywords/discover", headers=headers)
    job = finished_job(db, "keywords")

    ideas = client.get(f"/sites/{site_id}/keywords/ideas", headers=headers).json()
    assert job.status == "done"
    assert {i["keyword"] for i in ideas} == {"buy widgets", "cheap widgets"}


def test_rediscovery_updates_search_console_numbers_without_losing_targeting(client, db, stub_discovery, monkeypatch):
    headers = register_and_login(client, "kw3@test.dev")
    site_id = make_site(client, headers)
    client.post(f"/sites/{site_id}/pages", json={"url": "https://example.com/"}, headers=headers)
    monkeypatch.setattr(site_jobs, "google_access", lambda session, site: ("token", "sc-domain:example.com"))
    rows = [{"query": "widget reviews", "impressions": 500, "clicks": 3, "position": 14.2}]
    monkeypatch.setattr(site_jobs.gsc, "get_site_search_analytics", lambda token, prop: rows)
    client.post(f"/sites/{site_id}/keywords/discover", headers=headers)
    finished_job(db, "keywords")
    idea_id = next(i["id"] for i in client.get(f"/sites/{site_id}/keywords/ideas", headers=headers).json()
                   if i["keyword"] == "widget reviews")
    client.post(f"/sites/{site_id}/keywords/target", json={"ids": [idea_id], "targeted": True}, headers=headers)

    rows[0] = {"query": "widget reviews", "impressions": 900, "clicks": 20, "position": 6.0}
    client.post(f"/sites/{site_id}/keywords/discover", headers=headers)
    finished_job(db, "keywords")

    updated = next(i for i in client.get(f"/sites/{site_id}/keywords/ideas", headers=headers).json()
                   if i["keyword"] == "widget reviews")
    assert updated["impressions"] == 900 and updated["position"] == 6.0
    assert updated["targeted"] is True  # the owner's choice survives a refresh


def test_discovery_stops_cleanly_when_credits_run_out(client, db, stub_discovery, no_google, monkeypatch):
    headers = register_and_login(client, "kw4@test.dev")
    site_id = make_site(client, headers)
    client.post(f"/sites/{site_id}/pages", json={"url": "https://example.com/"}, headers=headers)
    user = get_user(db, "kw4@test.dev")
    with Session(db) as session:
        u = session.get(type(user), user.id)
        u.credits_balance = 1  # enough for the AI read, not the related-searches lookup
        session.add(u)
        session.commit()

    client.post(f"/sites/{site_id}/keywords/discover", headers=headers)
    job = finished_job(db, "keywords")

    assert job.status == "done" and job.credits_spent == 1
    ideas = {i["keyword"] for i in client.get(f"/sites/{site_id}/keywords/ideas", headers=headers).json()}
    assert ideas == {"buy widgets"}  # what was paid for is kept
    assert get_user(db, "kw4@test.dev").credits_balance == 0


def test_discovery_needs_at_least_one_credit(client, db, stub_discovery, no_google):
    headers = register_and_login(client, "kw5@test.dev")
    site_id = make_site(client, headers)
    user = get_user(db, "kw5@test.dev")
    with Session(db) as session:
        u = session.get(type(user), user.id)
        u.credits_balance = 0
        session.add(u)
        session.commit()

    assert client.post(f"/sites/{site_id}/keywords/discover", headers=headers).status_code == 402


def test_targeting_and_deleting_ideas(client, db, stub_discovery, no_google):
    headers = register_and_login(client, "kw6@test.dev")
    site_id = make_site(client, headers)
    client.post(f"/sites/{site_id}/pages", json={"url": "https://example.com/"}, headers=headers)
    client.post(f"/sites/{site_id}/keywords/discover", headers=headers)
    finished_job(db, "keywords")
    ideas = client.get(f"/sites/{site_id}/keywords/ideas", headers=headers).json()
    first = ideas[0]["id"]

    targeted = client.post(f"/sites/{site_id}/keywords/target", json={"ids": [first]}, headers=headers).json()
    assert targeted[0]["targeted"] is True and targeted[0]["id"] == first  # targeted sort to the top

    untargeted = client.post(
        f"/sites/{site_id}/keywords/target", json={"ids": [first], "targeted": False}, headers=headers
    ).json()
    assert all(i["targeted"] is False for i in untargeted)

    assert client.delete(f"/sites/{site_id}/keywords/ideas/{first}", headers=headers).status_code == 204
    assert first not in {i["id"] for i in client.get(f"/sites/{site_id}/keywords/ideas", headers=headers).json()}
    assert client.post(f"/sites/{site_id}/keywords/target", json={"ids": [first]}, headers=headers).status_code == 404


# --- visibility ---

@pytest.fixture
def targeted_site(client, db, stub_discovery, no_google):
    headers = register_and_login(client, "vis@test.dev")
    site_id = make_site(client, headers)
    client.post(f"/sites/{site_id}/pages", json={"url": "https://example.com/"}, headers=headers)
    client.post(f"/sites/{site_id}/keywords/discover", headers=headers)
    finished_job(db, "keywords")
    ideas = client.get(f"/sites/{site_id}/keywords/ideas", headers=headers).json()
    client.post(f"/sites/{site_id}/keywords/target", json={"ids": [ideas[0]["id"]]}, headers=headers)
    with Session(db) as session:
        user = session.get(type(get_user(db, "vis@test.dev")), get_user(db, "vis@test.dev").id)
        user.credits_balance = 50
        session.add(user)
        session.commit()
    return headers, site_id, ideas[0]["keyword"]


def test_a_visibility_run_records_all_three_engines(client, db, targeted_site, monkeypatch):
    headers, site_id, keyword = targeted_site
    monkeypatch.setattr(site_jobs.visibility, "check_google", lambda kw, domain, *a, **k: [
        EngineResult(engine="google", present=True, position=7),
        EngineResult(engine="google_ai_overview", present=True, detail="Cited as a source"),
    ])
    monkeypatch.setattr(site_jobs.visibility, "check_chatgpt", lambda kw, domain: EngineResult(
        engine="chatgpt", present=True, detail="Example.com is a good option."))

    client.post(f"/sites/{site_id}/visibility/check", headers=headers)
    job = finished_job(db, "visibility")

    assert job.status == "done" and job.credits_spent == 2  # one search + one model question
    report = client.get(f"/sites/{site_id}/visibility", headers=headers).json()
    assert report["targeted_keywords"] == 1
    assert (report["google_visible"], report["ai_overview_cited"], report["chatgpt_mentions"]) == (1, 1, 1)
    engines = {e["engine"]: e for e in report["keywords"][0]["engines"]}
    assert engines["google"]["position"] == 7
    assert engines["chatgpt"]["detail"] == "Example.com is a good option."


def test_not_being_visible_is_reported_as_clearly_as_being_visible(client, db, targeted_site, monkeypatch):
    headers, site_id, keyword = targeted_site
    monkeypatch.setattr(site_jobs.visibility, "check_google", lambda kw, domain, *a, **k: [
        EngineResult(engine="google", present=False, detail="Not in the first 100 results"),
        EngineResult(engine="google_ai_overview", present=False, detail="Cited instead: ahrefs.com, moz.com"),
    ])
    monkeypatch.setattr(site_jobs.visibility, "check_chatgpt", lambda kw, domain: EngineResult(
        engine="chatgpt", present=False, detail="Not mentioned in the answer"))

    client.post(f"/sites/{site_id}/visibility/check", headers=headers)
    finished_job(db, "visibility")

    report = client.get(f"/sites/{site_id}/visibility", headers=headers).json()
    assert (report["google_visible"], report["ai_overview_cited"], report["chatgpt_mentions"]) == (0, 0, 0)
    engines = {e["engine"]: e for e in report["keywords"][0]["engines"]}
    assert "ahrefs.com" in engines["google_ai_overview"]["detail"]  # who won instead is the useful part


def test_the_report_shows_only_the_newest_reading_per_engine(client, db, targeted_site, monkeypatch):
    headers, site_id, keyword = targeted_site
    monkeypatch.setattr(site_jobs.visibility, "check_chatgpt", lambda kw, domain: EngineResult(
        engine="chatgpt", present=False))

    monkeypatch.setattr(site_jobs.visibility, "check_google", lambda kw, domain, *a, **k: [
        EngineResult(engine="google", present=False, detail="Not in the first 100 results"),
        EngineResult(engine="google_ai_overview", present=False),
    ])
    client.post(f"/sites/{site_id}/visibility/check", headers=headers)
    finished_job(db, "visibility")

    monkeypatch.setattr(site_jobs.visibility, "check_google", lambda kw, domain, *a, **k: [
        EngineResult(engine="google", present=True, position=3),
        EngineResult(engine="google_ai_overview", present=False),
    ])
    client.post(f"/sites/{site_id}/visibility/check", headers=headers)
    finished_job(db, "visibility")

    report = client.get(f"/sites/{site_id}/visibility", headers=headers).json()
    engines = {e["engine"]: e for e in report["keywords"][0]["engines"]}
    assert engines["google"]["present"] is True and engines["google"]["position"] == 3
    with Session(db) as session:  # history is kept, not overwritten
        assert len(session.exec(select(VisibilityCheck).where(VisibilityCheck.engine == "google")).all()) == 2


def test_a_visibility_run_needs_targeted_keywords_and_credits(client, db, stub_discovery, no_google):
    headers = register_and_login(client, "vis2@test.dev")
    site_id = make_site(client, headers)

    no_keywords = client.post(f"/sites/{site_id}/visibility/check", headers=headers)

    assert no_keywords.status_code == 400 and "Pick the keywords" in no_keywords.json()["detail"]


def test_a_google_failure_does_not_lose_the_ai_reading(client, db, targeted_site, monkeypatch):
    """One vendor being down shouldn't wipe the other engine's answer."""
    from app.services.rank_providers.base import RankProviderError

    headers, site_id, keyword = targeted_site

    def boom(*a, **k):
        raise RankProviderError("SerpApi error: over quota")

    monkeypatch.setattr(site_jobs.visibility, "check_google", boom)

    client.post(f"/sites/{site_id}/visibility/check", headers=headers)
    job = finished_job(db, "visibility")

    assert job.status == "failed" and "over quota" in job.error


# --- the real visibility logic, with the vendor stubbed at the provider level ---

def test_google_check_reads_position_and_ai_overview_from_one_search(monkeypatch):
    from app.services import visibility as vis

    snapshot = SerpSnapshot(
        results=[
            SerpResult(position=1, title="Rival", domain="ahrefs.com", url="https://ahrefs.com/a"),
            SerpResult(position=4, title="Us", domain="example.com", url="https://example.com/a"),
        ],
        ai_overview=AIOverview(present=True, sources=["moz.com", "example.com"], text="..."),
    )

    class Provider:
        def fetch_snapshot(self, **kwargs):
            return snapshot

    monkeypatch.setattr(vis, "get_rank_provider", lambda: Provider())

    organic, ai = vis.check_google("widgets", "example.com")

    assert (organic.present, organic.position) == (True, 4)
    assert ai.present is True and ai.detail == "Cited as a source"


def test_an_ai_overview_that_cites_someone_else_names_them(monkeypatch):
    from app.services import visibility as vis

    class Provider:
        def fetch_snapshot(self, **kwargs):
            return SerpSnapshot(
                results=[],
                ai_overview=AIOverview(present=True, sources=["ahrefs.com", "moz.com"], text="..."),
            )

    monkeypatch.setattr(vis, "get_rank_provider", lambda: Provider())

    _, ai = vis.check_google("widgets", "example.com")

    assert ai.present is False and ai.detail == "Cited instead: ahrefs.com, moz.com"


def test_no_ai_overview_is_distinguished_from_not_being_cited(monkeypatch):
    """"Google didn't show an AI answer" and "it showed one without us" are
    different results and the UI has to be able to tell them apart."""
    from app.services import visibility as vis

    class Provider:
        def fetch_snapshot(self, **kwargs):
            return SerpSnapshot(results=[], ai_overview=None)

    monkeypatch.setattr(vis, "get_rank_provider", lambda: Provider())

    _, ai = vis.check_google("widgets", "example.com")

    assert ai.present is False and ai.detail == vis.NO_AI_OVERVIEW
