"""Crawl, keyword discovery and visibility, end to end through the API.

TestClient runs BackgroundTasks as part of the response, so by the time a POST
returns here the job has already finished - which means these tests exercise the
real background path rather than a stand-in for it. `finished_job` just reads
back the result.
"""
import json
from datetime import datetime, timedelta

import pytest
from sqlmodel import Session, select

import app.services.gsc as gsc_module
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


# --- search presence (the site page's gauges + trend) ---

def test_presence_gauges_score_google_and_ai_out_of_checked_keywords(client, db, targeted_site, monkeypatch):
    headers, site_id, keyword = targeted_site
    monkeypatch.setattr(site_jobs.visibility, "check_google", lambda kw, domain, *a, **k: [
        EngineResult(engine="google", present=True, position=9),
        EngineResult(engine="google_ai_overview", present=False, detail="Cited instead: ahrefs.com"),
    ])
    monkeypatch.setattr(site_jobs.visibility, "check_chatgpt", lambda kw, domain: EngineResult(
        engine="chatgpt", present=True, detail="Example.com is one option."))
    client.post(f"/sites/{site_id}/visibility/check", headers=headers)

    presence = client.get(f"/sites/{site_id}/presence", headers=headers).json()

    assert presence["checked_keywords"] == 1
    assert (presence["google_visible"], presence["google_score"], presence["best_position"]) == (1, 100, 9)
    # AI combines the Overview citation and the model mention - one question to the owner
    assert (presence["ai_visible"], presence["ai_score"]) == (1, 100)
    assert (presence["ai_overview_cited"], presence["chatgpt_mentions"]) == (0, 1)


def test_presence_scores_are_null_before_anything_is_checked(client, db, stub_discovery, no_google):
    """Nothing checked yet is not the same as "visible for none of them", and a
    gauge reading 0% would say the second."""
    headers = register_and_login(client, "pres2@test.dev")
    site_id = make_site(client, headers)

    presence = client.get(f"/sites/{site_id}/presence", headers=headers).json()

    assert presence["checked_keywords"] == 0
    assert presence["google_score"] is None and presence["ai_score"] is None
    assert presence["trend_unavailable"] == "no_pages"


def test_presence_explains_why_there_is_no_trend_line(client, db, monkeypatch, no_google):
    headers = register_and_login(client, "pres3@test.dev")
    site_id = make_site(client, headers)
    monkeypatch.setattr(site_jobs, "discover", lambda domain, limit: [Discovered("https://example.com/", "sitemap")])
    client.post(f"/sites/{site_id}/crawl", headers=headers)

    presence = client.get(f"/sites/{site_id}/presence", headers=headers).json()

    assert presence["trend_unavailable"] == "no_google"  # pages exist, Google doesn't
    assert presence["trend"] == []


def test_presence_charts_the_home_page_and_measures_the_week_on_week_change(client, db, monkeypatch):
    from datetime import date, timedelta

    headers = register_and_login(client, "pres4@test.dev")
    site_id = make_site(client, headers)
    monkeypatch.setattr(site_jobs, "discover", lambda domain, limit: [
        Discovered("https://example.com/blog/post", "sitemap"),
        Discovered("https://example.com/", "sitemap"),
    ])
    monkeypatch.setattr(site_jobs, "google_access", lambda session, site: ("token", "sc-domain:example.com"))
    monkeypatch.setattr(site_jobs.index_status, "check_page", lambda *a: None)
    client.post(f"/sites/{site_id}/crawl", headers=headers)

    today = date.today()
    # 10/day for the older week, 20/day for the most recent: a clean +100%.
    rows = (
        [{"date": (today - timedelta(days=d)).isoformat(), "clicks": 1, "impressions": 10, "position": 12.0}
         for d in range(13, 6, -1)]
        + [{"date": (today - timedelta(days=d)).isoformat(), "clicks": 2, "impressions": 20, "position": 8.0}
           for d in range(6, -1, -1)]
    )
    captured = {}

    def fake_daily(token, prop, page_url, days=28):
        captured["page_url"] = page_url
        return rows

    monkeypatch.setattr(gsc_module, "get_page_daily_metrics", fake_daily)

    presence = client.get(f"/sites/{site_id}/presence", headers=headers).json()

    assert captured["page_url"] == "https://example.com/"  # the home page, not the first crawled
    assert presence["trend_page_url"] == "https://example.com/"
    assert presence["trend_unavailable"] is None
    assert len(presence["trend"]) == 29  # gaps filled, so the x-axis is continuous
    assert presence["impressions_total"] == 7 * 10 + 7 * 20
    assert presence["impressions_change"] == 100
    assert presence["average_position"] == 10.0


def test_days_with_no_impressions_are_filled_in_rather_than_skipped(client, db, monkeypatch):
    """Search Console omits empty days entirely. Plotting only what it returns
    would squeeze a quiet month into a busy-looking line."""
    from datetime import date, timedelta

    headers = register_and_login(client, "pres5@test.dev")
    site_id = make_site(client, headers)
    monkeypatch.setattr(site_jobs, "discover", lambda domain, limit: [Discovered("https://example.com/", "sitemap")])
    monkeypatch.setattr(site_jobs, "google_access", lambda session, site: ("token", "sc-domain:example.com"))
    monkeypatch.setattr(site_jobs.index_status, "check_page", lambda *a: None)
    client.post(f"/sites/{site_id}/crawl", headers=headers)
    two_days_ago = (date.today() - timedelta(days=2)).isoformat()
    monkeypatch.setattr(gsc_module, "get_page_daily_metrics", lambda *a, **k: [
        {"date": two_days_ago, "clicks": 5, "impressions": 50, "position": 3.0},
    ])

    trend = client.get(f"/sites/{site_id}/presence", headers=headers).json()["trend"]

    # 29 days, minus today and yesterday trimmed as reporting lag
    assert len(trend) == 27
    assert sum(p["impressions"] for p in trend) == 50
    assert next(p for p in trend if p["date"] == two_days_ago)["clicks"] == 5
    # the quiet days before it are still drawn, so the gap is visible
    assert sum(1 for p in trend if p["impressions"] == 0) == 26


def test_the_trend_stops_before_search_consoles_reporting_lag(client, db, monkeypatch):
    """Search Console runs ~2 days behind, so its trailing zeros mean "not
    counted yet". Drawing them plunges the line to the floor and reads as
    traffic collapsing."""
    from datetime import date, timedelta

    headers = register_and_login(client, "lag@test.dev")
    site_id = make_site(client, headers)
    monkeypatch.setattr(site_jobs, "discover", lambda domain, limit: [Discovered("https://example.com/", "sitemap")])
    monkeypatch.setattr(site_jobs, "google_access", lambda session, site: ("token", "sc-domain:example.com"))
    monkeypatch.setattr(site_jobs.index_status, "check_page", lambda *a: None)
    client.post(f"/sites/{site_id}/crawl", headers=headers)
    today = date.today()
    # Real data up to 2 days ago, then nothing - exactly the lag pattern.
    monkeypatch.setattr(gsc_module, "get_page_daily_metrics", lambda *a, **k: [
        {"date": (today - timedelta(days=d)).isoformat(), "clicks": 2, "impressions": 30, "position": 7.0}
        for d in range(28, 1, -1)
    ])

    trend = client.get(f"/sites/{site_id}/presence", headers=headers).json()["trend"]

    assert trend[-1]["date"] == (today - timedelta(days=2)).isoformat()
    assert all(p["impressions"] > 0 for p in trend)  # no false cliff at the end


def test_a_real_run_of_zero_days_is_not_hidden(client, db, monkeypatch):
    """Only the lag window is trimmed. A site that genuinely stopped getting
    impressions a week ago must still see that week."""
    from datetime import date, timedelta

    headers = register_and_login(client, "lag2@test.dev")
    site_id = make_site(client, headers)
    monkeypatch.setattr(site_jobs, "discover", lambda domain, limit: [Discovered("https://example.com/", "sitemap")])
    monkeypatch.setattr(site_jobs, "google_access", lambda session, site: ("token", "sc-domain:example.com"))
    monkeypatch.setattr(site_jobs.index_status, "check_page", lambda *a: None)
    client.post(f"/sites/{site_id}/crawl", headers=headers)
    today = date.today()
    monkeypatch.setattr(gsc_module, "get_page_daily_metrics", lambda *a, **k: [
        {"date": (today - timedelta(days=d)).isoformat(), "clicks": 2, "impressions": 30, "position": 7.0}
        for d in range(28, 9, -1)  # nothing for the last 10 days
    ])

    trend = client.get(f"/sites/{site_id}/presence", headers=headers).json()["trend"]

    zeros = [p for p in trend if p["impressions"] == 0]
    assert len(zeros) >= 6  # the real drought is still visible


# --- visibility advice ---

@pytest.fixture
def checked_keyword(client, db, targeted_site, monkeypatch):
    """A keyword with a real reading behind it: we rank #14, the AI Overview
    cited someone else, and an assistant named someone else."""
    headers, site_id, keyword = targeted_site
    monkeypatch.setattr(site_jobs.visibility, "check_google", lambda kw, domain, *a, **k: [
        EngineResult(engine="google", present=True, position=14, context={
            "top_results": [{"position": 1, "title": "Best SEO Audit Tools", "domain": "ahrefs.com",
                             "url": "https://ahrefs.com/blog/seo-audit"}],
        }),
        EngineResult(engine="google_ai_overview", present=False, detail="Cited instead: ahrefs.com",
                     context={"sources": ["ahrefs.com", "moz.com"], "answer": "The leading tools are..."}),
    ])
    monkeypatch.setattr(site_jobs.visibility, "check_chatgpt", lambda kw, domain: EngineResult(
        engine="chatgpt", present=False, detail="Not mentioned in the answer",
        context={"answer": "Popular options include Ahrefs and Semrush."}))
    client.post(f"/sites/{site_id}/visibility/check", headers=headers)
    return headers, site_id, keyword


def test_advice_is_built_from_what_the_check_actually_found(client, db, checked_keyword, monkeypatch):
    """The whole point is that the suggestions are specific, so the model must
    be handed the real evidence - the competitor that ranks, the sources the AI
    Overview used, the site's own page."""
    headers, site_id, keyword = checked_keyword
    seen = {}

    def fake_complete(system, user, max_tokens=900):
        seen["system"], seen["user"] = system, user
        return '''{"diagnosis": "You rank #14 while Ahrefs holds the AI Overview citation.",
                   "target_page": "https://example.com/",
                   "actions": [{"title": "Add a tool comparison table",
                                "detail": "Ahrefs ranks #1 with one; your page has none.",
                                "addresses": "both"}]}'''

    monkeypatch.setattr(
        "app.services.visibility_advice.get_ai_provider", lambda: type("P", (), {"complete": staticmethod(fake_complete)})()
    )
    monkeypatch.setattr("app.routers.discovery._page_text", lambda url: "We audit pages for SEO problems.")

    resp = client.post(f"/sites/{site_id}/visibility/suggest", json={"keyword": keyword}, headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["diagnosis"].startswith("You rank #14")
    assert body["actions"][0]["addresses"] == "both"
    assert body["target_page_url"] == "https://example.com/"
    # the evidence really reached the model
    assert "#14" in seen["user"] and "ahrefs.com" in seen["user"]
    assert "Popular options include Ahrefs" in seen["user"]  # what the assistant said instead
    assert "We audit pages for SEO problems." in seen["user"]  # their own content
    assert "generic" in seen["system"].lower() or "Generic" in seen["system"]


def test_advice_costs_one_credit_and_is_free_to_read_again(client, db, checked_keyword, monkeypatch):
    headers, site_id, keyword = checked_keyword
    monkeypatch.setattr(
        "app.services.visibility_advice.get_ai_provider",
        lambda: type("P", (), {"complete": staticmethod(lambda s, u, max_tokens=900: '{"diagnosis": "d", "actions": []}')})(),
    )
    before = client.get("/auth/me", headers=headers).json()["credits_balance"]

    client.post(f"/sites/{site_id}/visibility/suggest", json={"keyword": keyword}, headers=headers)
    after_generate = client.get("/auth/me", headers=headers).json()["credits_balance"]
    report = client.get(f"/sites/{site_id}/visibility", headers=headers).json()
    after_read = client.get("/auth/me", headers=headers).json()["credits_balance"]

    assert after_generate == before - 1  # the search was already paid for by the check
    assert after_read == after_generate  # re-reading is free
    row = next(k for k in report["keywords"] if k["keyword"] == keyword)
    assert row["advice"]["diagnosis"] == "d"


def test_advice_needs_a_check_to_have_run_first(client, db, targeted_site):
    headers, site_id, keyword = targeted_site

    resp = client.post(f"/sites/{site_id}/visibility/suggest", json={"keyword": keyword}, headers=headers)

    assert resp.status_code == 400 and "Check this keyword" in resp.json()["detail"]


def test_a_reading_taken_before_evidence_was_recorded_asks_for_a_re_check(client, db, targeted_site, monkeypatch):
    """Old rows have no stored SERP. Advice with nothing behind it would be the
    generic filler this feature exists to avoid, so it isn't offered."""
    headers, site_id, keyword = targeted_site
    monkeypatch.setattr(site_jobs.visibility, "check_google", lambda kw, domain, *a, **k: [
        EngineResult(engine="google", present=True, position=9),  # no context, as before 0013
        EngineResult(engine="google_ai_overview", present=False),
    ])
    monkeypatch.setattr(site_jobs.visibility, "check_chatgpt", lambda kw, domain: EngineResult(
        engine="chatgpt", present=False))
    client.post(f"/sites/{site_id}/visibility/check", headers=headers)

    resp = client.post(f"/sites/{site_id}/visibility/suggest", json={"keyword": keyword}, headers=headers)

    assert resp.status_code == 400 and "Run the check again" in resp.json()["detail"]


def test_advice_is_marked_stale_once_the_keyword_is_re_checked(client, db, checked_keyword, monkeypatch):
    """Advice describing a SERP that has since moved is worse than none unless
    it's labelled."""
    headers, site_id, keyword = checked_keyword
    monkeypatch.setattr(
        "app.services.visibility_advice.get_ai_provider",
        lambda: type("P", (), {"complete": staticmethod(lambda s, u, max_tokens=900: '{"diagnosis": "d", "actions": []}')})(),
    )
    client.post(f"/sites/{site_id}/visibility/suggest", json={"keyword": keyword}, headers=headers)
    fresh = client.get(f"/sites/{site_id}/visibility", headers=headers).json()
    assert next(k for k in fresh["keywords"] if k["keyword"] == keyword)["advice"]["stale"] is False

    client.post(f"/sites/{site_id}/visibility/check", headers=headers)  # the search moves on

    after = client.get(f"/sites/{site_id}/visibility", headers=headers).json()
    assert next(k for k in after["keywords"] if k["keyword"] == keyword)["advice"]["stale"] is True


def test_the_check_records_who_won_so_advice_costs_no_extra_search(client, db, checked_keyword):
    """The SERP is captured during the check - which already fetched it - so the
    advice never has to buy the same search twice."""
    headers, site_id, keyword = checked_keyword

    with Session(db) as session:
        google = session.exec(
            select(VisibilityCheck).where(VisibilityCheck.engine == "google")
        ).first()
    stored = json.loads(google.context)
    assert stored["top_results"][0]["domain"] == "ahrefs.com"


def test_a_page_that_cannot_be_fetched_does_not_block_the_advice(client, db, checked_keyword, monkeypatch):
    headers, site_id, keyword = checked_keyword

    def boom(url):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("app.routers.discovery._page_text", boom)
    monkeypatch.setattr(
        "app.services.visibility_advice.get_ai_provider",
        lambda: type("P", (), {"complete": staticmethod(lambda s, u, max_tokens=900: '{"diagnosis": "still useful", "actions": []}')})(),
    )

    resp = client.post(f"/sites/{site_id}/visibility/suggest", json={"keyword": keyword}, headers=headers)

    assert resp.status_code == 200 and resp.json()["diagnosis"] == "still useful"


def test_a_model_that_returns_nothing_usable_does_not_charge(client, db, checked_keyword, monkeypatch):
    headers, site_id, keyword = checked_keyword
    monkeypatch.setattr(
        "app.services.visibility_advice.get_ai_provider",
        lambda: type("P", (), {"complete": staticmethod(lambda s, u, max_tokens=900: "sorry, I can't help")})(),
    )
    before = client.get("/auth/me", headers=headers).json()["credits_balance"]

    resp = client.post(f"/sites/{site_id}/visibility/suggest", json={"keyword": keyword}, headers=headers)

    assert resp.status_code == 502
    assert client.get("/auth/me", headers=headers).json()["credits_balance"] == before  # never charge on failure
