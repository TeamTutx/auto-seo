from datetime import datetime, timedelta

from sqlmodel import Session

from app.models import Audit, Check, CheckStatus, KeywordRank
from tests.conftest import register_and_login


def _insert_audit(db, page_id, checks):
    """checks: list of (check_type, status, message, suggested_fix)."""
    with Session(db) as session:
        audit = Audit(page_id=page_id, score=50)
        session.add(audit)
        session.commit()
        session.refresh(audit)
        for check_type, status, message, suggested_fix in checks:
            session.add(
                Check(audit_id=audit.id, check_type=check_type, status=status, message=message, suggested_fix=suggested_fix)
            )
        session.commit()
        return audit.id


def _insert_rank(db, page_id, keyword, rank_position, checked_at=None):
    with Session(db) as session:
        rank = KeywordRank(page_id=page_id, keyword=keyword, rank_position=rank_position)
        if checked_at is not None:
            rank.checked_at = checked_at
        session.add(rank)
        session.commit()


def _make_site_and_page(client, headers, domain="example.com"):
    site = client.post("/sites", json={"domain": domain}, headers=headers).json()
    page = client.post(f"/sites/{site['id']}/pages", json={"url": f"https://{domain}/"}, headers=headers).json()
    return site["id"], page["id"]


def test_failing_check_becomes_a_high_severity_opportunity(client, db):
    headers = register_and_login(client, "opp1@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_audit(
        db, page_id, [("meta_description", CheckStatus.fail, "Missing meta description.", "Add a 150-160 char summary.")]
    )

    resp = client.get(f"/sites/{site_id}/opportunities", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["type"] == "audit_fail"
    assert body[0]["severity"] == "high"
    assert body[0]["check_type"] == "meta_description"
    assert body[0]["suggested_fix"] == "Add a 150-160 char summary."


def test_warning_check_becomes_a_medium_severity_opportunity(client, db):
    headers = register_and_login(client, "opp2@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_audit(db, page_id, [("readability", CheckStatus.warning, "A bit dense.", None)])

    resp = client.get(f"/sites/{site_id}/opportunities", headers=headers)
    body = resp.json()
    assert len(body) == 1
    assert body[0]["type"] == "audit_warning"
    assert body[0]["severity"] == "medium"


def test_passing_checks_produce_no_opportunities(client, db):
    headers = register_and_login(client, "opp3@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_audit(db, page_id, [("title_tag", CheckStatus.pass_, "Good title.", None)])

    resp = client.get(f"/sites/{site_id}/opportunities", headers=headers)
    assert resp.json() == []


def test_only_the_latest_audit_is_considered(client, db):
    headers = register_and_login(client, "opp4@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_audit(db, page_id, [("title_tag", CheckStatus.fail, "Missing title.", None)])
    _insert_audit(db, page_id, [("title_tag", CheckStatus.pass_, "Fixed.", None)])  # most recent

    resp = client.get(f"/sites/{site_id}/opportunities", headers=headers)
    assert resp.json() == []


def test_keyword_not_found_is_high_severity(client, db):
    headers = register_and_login(client, "opp5@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_rank(db, page_id, "vitamin c serum", None)

    resp = client.get(f"/sites/{site_id}/opportunities", headers=headers)
    body = resp.json()
    assert len(body) == 1
    assert body[0]["type"] == "keyword_not_found"
    assert body[0]["severity"] == "high"
    assert body[0]["keyword"] == "vitamin c serum"


def test_keyword_outside_top_10_is_medium_severity(client, db):
    headers = register_and_login(client, "opp6@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_rank(db, page_id, "vitamin c serum", 25)

    resp = client.get(f"/sites/{site_id}/opportunities", headers=headers)
    body = resp.json()
    assert len(body) == 1
    assert body[0]["type"] == "keyword_low_rank"
    assert body[0]["severity"] == "medium"


def test_keyword_in_top_10_is_not_an_opportunity(client, db):
    headers = register_and_login(client, "opp7@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_rank(db, page_id, "vitamin c serum", 3)

    resp = client.get(f"/sites/{site_id}/opportunities", headers=headers)
    assert resp.json() == []


def test_rank_drop_since_previous_check_is_flagged(client, db):
    headers = register_and_login(client, "opp8@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    now = datetime.utcnow()
    _insert_rank(db, page_id, "vitamin c serum", 4, checked_at=now - timedelta(days=1))
    _insert_rank(db, page_id, "vitamin c serum", 9, checked_at=now)  # latest - dropped 5 spots but still top 10

    resp = client.get(f"/sites/{site_id}/opportunities", headers=headers)
    body = resp.json()
    types = {o["type"] for o in body}
    assert "keyword_rank_drop" in types
    drop = next(o for o in body if o["type"] == "keyword_rank_drop")
    assert "4" in drop["detail"] and "9" in drop["detail"]


def test_small_rank_change_is_not_flagged_as_a_drop(client, db):
    headers = register_and_login(client, "opp9@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    now = datetime.utcnow()
    _insert_rank(db, page_id, "vitamin c serum", 4, checked_at=now - timedelta(days=1))
    _insert_rank(db, page_id, "vitamin c serum", 5, checked_at=now)  # only 1 spot worse

    resp = client.get(f"/sites/{site_id}/opportunities", headers=headers)
    assert resp.json() == []


def test_opportunities_are_sorted_high_severity_first(client, db):
    headers = register_and_login(client, "opp10@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_audit(db, page_id, [("readability", CheckStatus.warning, "meh", None)])  # medium
    _insert_rank(db, page_id, "vitamin c serum", None)  # high

    resp = client.get(f"/sites/{site_id}/opportunities", headers=headers)
    body = resp.json()
    assert [o["severity"] for o in body] == ["high", "medium"]


def test_opportunities_are_scoped_to_the_owning_user(client, db):
    headers1 = register_and_login(client, "opp11a@test.dev")
    headers2 = register_and_login(client, "opp11b@test.dev")
    site_id, page_id = _make_site_and_page(client, headers1, domain="owned-by-1.com")
    _insert_rank(db, page_id, "vitamin c serum", None)

    resp = client.get(f"/sites/{site_id}/opportunities", headers=headers2)
    assert resp.status_code == 404
