from datetime import datetime, timedelta

from sqlmodel import Session

from app.models import Audit, KeywordRank
from app.services.site_health import get_site_health
from tests.conftest import register_and_login


def _make_site_and_pages(client, headers, domain="example.com", count=1):
    site = client.post("/sites", json={"domain": domain}, headers=headers).json()
    page_ids = []
    for i in range(count):
        page = client.post(
            f"/sites/{site['id']}/pages", json={"url": f"https://{domain}/page-{i}"}, headers=headers
        ).json()
        page_ids.append(page["id"])
    return site["id"], page_ids


def _insert_audit(db, page_id, score, created_at):
    with Session(db) as session:
        session.add(Audit(page_id=page_id, score=score, created_at=created_at))
        session.commit()


def _insert_rank(db, page_id, keyword, rank_position, checked_at):
    with Session(db) as session:
        session.add(KeywordRank(page_id=page_id, keyword=keyword, rank_position=rank_position, checked_at=checked_at))
        session.commit()


def test_score_trend_averages_across_pages_as_of_each_audit(client, db):
    headers = register_and_login(client, "health1@test.dev")
    site_id, [page_a, page_b] = _make_site_and_pages(client, headers, count=2)

    now = datetime.utcnow()
    _insert_audit(db, page_a, 60, now - timedelta(days=2))
    _insert_audit(db, page_b, 80, now - timedelta(days=1))
    _insert_audit(db, page_a, 90, now)

    with Session(db) as session:
        health = get_site_health(session, site_id)

    assert [p.score for p in health.score_trend] == [60, 70, 85]


def test_score_movements_ranks_biggest_win_and_loss(client, db):
    headers = register_and_login(client, "health2@test.dev")
    site_id, [page_a, page_b] = _make_site_and_pages(client, headers, count=2)

    now = datetime.utcnow()
    _insert_audit(db, page_a, 50, now - timedelta(days=1))
    _insert_audit(db, page_a, 80, now)  # +30 win

    _insert_audit(db, page_b, 90, now - timedelta(days=1))
    _insert_audit(db, page_b, 70, now)  # -20 loss

    with Session(db) as session:
        health = get_site_health(session, site_id)

    assert len(health.score_wins) == 1
    assert health.score_wins[0].delta == 30
    assert len(health.score_losses) == 1
    assert health.score_losses[0].delta == -20


def test_score_movements_requires_at_least_two_audits(client, db):
    headers = register_and_login(client, "health3@test.dev")
    site_id, [page_a] = _make_site_and_pages(client, headers, count=1)
    _insert_audit(db, page_a, 60, datetime.utcnow())

    with Session(db) as session:
        health = get_site_health(session, site_id)

    assert health.score_wins == []
    assert health.score_losses == []


def test_keyword_movement_improved_rank_is_a_win(client, db):
    headers = register_and_login(client, "health4@test.dev")
    site_id, [page_a] = _make_site_and_pages(client, headers, count=1)

    now = datetime.utcnow()
    _insert_rank(db, page_a, "vitamin c serum", 20, now - timedelta(days=1))
    _insert_rank(db, page_a, "vitamin c serum", 5, now)  # improved by 15

    with Session(db) as session:
        health = get_site_health(session, site_id)

    assert len(health.keyword_wins) == 1
    assert health.keyword_wins[0].delta == 15
    assert health.keyword_wins[0].previous_rank == 20
    assert health.keyword_wins[0].new_rank == 5


def test_keyword_movement_worse_rank_is_a_loss(client, db):
    headers = register_and_login(client, "health5@test.dev")
    site_id, [page_a] = _make_site_and_pages(client, headers, count=1)

    now = datetime.utcnow()
    _insert_rank(db, page_a, "vitamin c serum", 5, now - timedelta(days=1))
    _insert_rank(db, page_a, "vitamin c serum", 20, now)  # dropped

    with Session(db) as session:
        health = get_site_health(session, site_id)

    assert len(health.keyword_losses) == 1
    assert health.keyword_losses[0].delta == -15


def test_keyword_newly_found_is_a_win_and_newly_lost_is_a_loss(client, db):
    headers = register_and_login(client, "health6@test.dev")
    site_id, [page_a] = _make_site_and_pages(client, headers, count=1)

    now = datetime.utcnow()
    _insert_rank(db, page_a, "found me", None, now - timedelta(days=1))
    _insert_rank(db, page_a, "found me", 8, now)

    _insert_rank(db, page_a, "lost me", 8, now - timedelta(days=1))
    _insert_rank(db, page_a, "lost me", None, now)

    with Session(db) as session:
        health = get_site_health(session, site_id)

    win_keywords = {m.keyword for m in health.keyword_wins}
    loss_keywords = {m.keyword for m in health.keyword_losses}
    assert "found me" in win_keywords
    assert "lost me" in loss_keywords


def test_unchanged_keyword_rank_is_not_a_movement(client, db):
    headers = register_and_login(client, "health7@test.dev")
    site_id, [page_a] = _make_site_and_pages(client, headers, count=1)

    now = datetime.utcnow()
    _insert_rank(db, page_a, "steady keyword", 7, now - timedelta(days=1))
    _insert_rank(db, page_a, "steady keyword", 7, now)

    with Session(db) as session:
        health = get_site_health(session, site_id)

    assert health.keyword_wins == []
    assert health.keyword_losses == []


def test_health_endpoint_is_scoped_to_the_owning_user(client, db):
    headers1 = register_and_login(client, "health8a@test.dev")
    headers2 = register_and_login(client, "health8b@test.dev")
    site_id, _ = _make_site_and_pages(client, headers1, domain="owned-by-1.com")

    resp = client.get(f"/sites/{site_id}/health", headers=headers2)
    assert resp.status_code == 404


def test_health_endpoint_returns_full_shape(client, db):
    headers = register_and_login(client, "health9@test.dev")
    site_id, [page_a] = _make_site_and_pages(client, headers, count=1)
    now = datetime.utcnow()
    _insert_audit(db, page_a, 60, now - timedelta(days=1))
    _insert_audit(db, page_a, 75, now)

    resp = client.get(f"/sites/{site_id}/health", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "score_trend", "score_wins", "score_losses", "keyword_wins", "keyword_losses", "top_opportunities",
    }
    assert body["score_wins"][0]["delta"] == 15
