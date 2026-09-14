from sqlmodel import Session, select

from app.models import AppliedFix, Audit, Check, CheckStatus, KeywordRank, OpportunityType, Page, User
from app.services.applied_fixes import mark_applied, verify_applied_fixes_for_audit, verify_applied_fixes_for_keyword
from tests.conftest import register_and_login


def _make_site_and_page(client, headers, domain="example.com"):
    site = client.post("/sites", json={"domain": domain}, headers=headers).json()
    page = client.post(f"/sites/{site['id']}/pages", json={"url": f"https://{domain}/"}, headers=headers).json()
    return site["id"], page["id"]


def _get_user_id(db, email):
    with Session(db) as session:
        return session.exec(select(User).where(User.email == email)).first().id


def _insert_audit(db, page_id, checks):
    with Session(db) as session:
        audit = Audit(page_id=page_id, score=50)
        session.add(audit)
        session.commit()
        session.refresh(audit)
        for check_type, status_, message in checks:
            session.add(Check(audit_id=audit.id, check_type=check_type, status=status_, message=message))
        session.commit()
        return audit.id


def _insert_rank(db, page_id, keyword, rank_position, checked_at=None):
    with Session(db) as session:
        rank = KeywordRank(page_id=page_id, keyword=keyword, rank_position=rank_position)
        if checked_at is not None:
            rank.checked_at = checked_at
        session.add(rank)
        session.commit()
        session.refresh(rank)
        return rank


def test_mark_applied_captures_audit_baseline(client, db):
    headers = register_and_login(client, "af1@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_audit(db, page_id, [("meta_description", CheckStatus.fail, "Missing.")])

    with Session(db) as session:
        page = session.get(Page, page_id)
        fix = mark_applied(session, page, OpportunityType.audit_fail, "meta_description", None)

    assert fix.baseline_score == 50
    assert fix.resolved is False


def test_mark_applied_captures_keyword_baseline(client, db):
    headers = register_and_login(client, "af2@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_rank(db, page_id, "vitamin c serum", None)

    with Session(db) as session:
        page = session.get(Page, page_id)
        fix = mark_applied(session, page, OpportunityType.keyword_not_found, None, "vitamin c serum")

    assert fix.baseline_rank is None
    assert fix.resolved is False


def test_verify_applied_fixes_for_audit_resolves_when_check_now_passes(client, db):
    headers = register_and_login(client, "af3@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    old_audit_id = _insert_audit(db, page_id, [("meta_description", CheckStatus.fail, "Missing.")])
    user_id = _get_user_id(db, "af3@test.dev")

    with Session(db) as session:
        page = session.get(Page, page_id)
        mark_applied(session, page, OpportunityType.audit_fail, "meta_description", None)

    with Session(db) as session:
        page = session.get(Page, page_id)
        new_audit = Audit(page_id=page_id, score=80)
        session.add(new_audit)
        session.commit()
        session.refresh(new_audit)
        session.add(Check(audit_id=new_audit.id, check_type="meta_description", status=CheckStatus.pass_, message="Good now."))
        session.commit()

        alerts = verify_applied_fixes_for_audit(session, user_id, page, new_audit)
        assert len(alerts) == 1
        assert alerts[0].alert_type == "fix_verified"

    with Session(db) as session:
        fixes = session.exec(select(AppliedFix).where(AppliedFix.page_id == page_id)).all()
        assert fixes[0].resolved is True


def test_verify_applied_fixes_for_audit_does_not_resolve_if_still_failing(client, db):
    headers = register_and_login(client, "af4@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_audit(db, page_id, [("meta_description", CheckStatus.fail, "Missing.")])
    user_id = _get_user_id(db, "af4@test.dev")

    with Session(db) as session:
        page = session.get(Page, page_id)
        mark_applied(session, page, OpportunityType.audit_fail, "meta_description", None)

    with Session(db) as session:
        page = session.get(Page, page_id)
        new_audit = Audit(page_id=page_id, score=55)
        session.add(new_audit)
        session.commit()
        session.refresh(new_audit)
        session.add(Check(audit_id=new_audit.id, check_type="meta_description", status=CheckStatus.warning, message="Still short."))
        session.commit()

        alerts = verify_applied_fixes_for_audit(session, user_id, page, new_audit)

    assert alerts == []


def test_verify_applied_fixes_for_keyword_resolves_when_found(client, db):
    headers = register_and_login(client, "af5@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_rank(db, page_id, "vitamin c serum", None)
    user_id = _get_user_id(db, "af5@test.dev")

    with Session(db) as session:
        page = session.get(Page, page_id)
        mark_applied(session, page, OpportunityType.keyword_not_found, None, "vitamin c serum")

    new_rank = _insert_rank(db, page_id, "vitamin c serum", 7)

    with Session(db) as session:
        page = session.get(Page, page_id)
        rank = session.get(KeywordRank, new_rank.id)
        alerts = verify_applied_fixes_for_keyword(session, user_id, page, rank)
        assert len(alerts) == 1
        assert "#7" in alerts[0].message
        assert "not found" in alerts[0].message


def test_verify_applied_fixes_for_keyword_does_not_resolve_while_still_not_found(client, db):
    headers = register_and_login(client, "af6@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_rank(db, page_id, "vitamin c serum", None)
    user_id = _get_user_id(db, "af6@test.dev")

    with Session(db) as session:
        page = session.get(Page, page_id)
        mark_applied(session, page, OpportunityType.keyword_not_found, None, "vitamin c serum")

    new_rank = _insert_rank(db, page_id, "vitamin c serum", None)

    with Session(db) as session:
        page = session.get(Page, page_id)
        rank = session.get(KeywordRank, new_rank.id)
        alerts = verify_applied_fixes_for_keyword(session, user_id, page, rank)

    assert alerts == []


def test_verify_applied_fixes_for_low_rank_keyword_requires_top_10(client, db):
    headers = register_and_login(client, "af7@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_rank(db, page_id, "vitamin c serum", 25)
    user_id = _get_user_id(db, "af7@test.dev")

    with Session(db) as session:
        page = session.get(Page, page_id)
        mark_applied(session, page, OpportunityType.keyword_low_rank, None, "vitamin c serum")

    # improved but still outside the top 10 - should NOT resolve yet
    still_low = _insert_rank(db, page_id, "vitamin c serum", 15)
    with Session(db) as session:
        page = session.get(Page, page_id)
        rank = session.get(KeywordRank, still_low.id)
        assert verify_applied_fixes_for_keyword(session, user_id, page, rank) == []

    # now inside the top 10 - should resolve
    now_good = _insert_rank(db, page_id, "vitamin c serum", 8)
    with Session(db) as session:
        page = session.get(Page, page_id)
        rank = session.get(KeywordRank, now_good.id)
        alerts = verify_applied_fixes_for_keyword(session, user_id, page, rank)
    assert len(alerts) == 1
