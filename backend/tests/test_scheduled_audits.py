from sqlmodel import Session, select

import app.services.scheduled_audits as scheduled_audits
from app.models import Alert, Audit, Check, CheckStatus, PlanTier, User
from app.services.scheduled_audits import run_scheduled_audits
from tests.conftest import register_and_login


def _insert_audit_with_session(session, page_id, score, failed_check_types):
    audit = Audit(page_id=page_id, score=score)
    session.add(audit)
    session.commit()
    session.refresh(audit)
    for check_type in failed_check_types:
        session.add(Check(audit_id=audit.id, check_type=check_type, status=CheckStatus.fail, message="bad"))
    session.add(Check(audit_id=audit.id, check_type="ok_check", status=CheckStatus.pass_, message="fine"))
    session.commit()
    return audit


def _insert_audit(db, page_id, score, failed_check_types):
    """For a *previous* audit that must exist before run_scheduled_audits runs."""
    with Session(db) as session:
        return _insert_audit_with_session(session, page_id, score, failed_check_types)


def _new_audit_factory(score, failed_check_types):
    """A fake audit_page(session, page_id) that inserts using the SAME
    session run_scheduled_audits passes in - matching the real audit_page's
    signature. Using a separate Session(db) here would return a detached
    object the caller can no longer read attributes from once that
    session closes."""

    def _fake(session, page_id):
        return _insert_audit_with_session(session, page_id, score, failed_check_types)

    return _fake


def _set_plan(db, email, plan):
    with Session(db) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        user.plan = plan
        session.add(user)
        session.commit()


def _setup_page(client, db, email, plan=PlanTier.pro):
    headers = register_and_login(client, email)
    _set_plan(db, email, plan)
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()
    page = client.post(f"/sites/{site['id']}/pages", json={"url": "https://example.com/"}, headers=headers).json()
    return headers, page["id"]


def test_score_drop_creates_an_alert(client, db, monkeypatch):
    headers, page_id = _setup_page(client, db, "sched1@test.dev")
    _insert_audit(db, page_id, score=80, failed_check_types=[])

    monkeypatch.setattr(scheduled_audits, "audit_page", _new_audit_factory(score=60, failed_check_types=[]))

    with Session(db) as session:
        count = run_scheduled_audits(session)
    assert count == 1

    with Session(db) as session:
        alerts = session.exec(select(Alert).where(Alert.page_id == page_id)).all()
    assert len(alerts) == 1
    assert alerts[0].alert_type == "score_drop"
    assert "80 to 60" in alerts[0].message


def test_small_score_change_does_not_alert(client, db, monkeypatch):
    headers, page_id = _setup_page(client, db, "sched2@test.dev")
    _insert_audit(db, page_id, score=80, failed_check_types=[])

    monkeypatch.setattr(scheduled_audits, "audit_page", _new_audit_factory(score=75, failed_check_types=[]))

    with Session(db) as session:
        count = run_scheduled_audits(session)
    assert count == 0


def test_newly_failing_check_creates_an_alert(client, db, monkeypatch):
    headers, page_id = _setup_page(client, db, "sched3@test.dev")
    _insert_audit(db, page_id, score=80, failed_check_types=["meta_description"])

    monkeypatch.setattr(
        scheduled_audits,
        "audit_page",
        _new_audit_factory(score=78, failed_check_types=["meta_description", "title_tag"]),
    )

    with Session(db) as session:
        count = run_scheduled_audits(session)
    assert count == 1

    with Session(db) as session:
        alerts = session.exec(select(Alert).where(Alert.page_id == page_id)).all()
    assert alerts[0].alert_type == "new_fail"
    assert "title_tag" in alerts[0].message
    assert "meta_description" not in alerts[0].message  # already failing before, not new


def test_free_plan_pages_are_skipped(client, db, monkeypatch):
    headers, page_id = _setup_page(client, db, "sched4@test.dev", plan=PlanTier.free)
    _insert_audit(db, page_id, score=80, failed_check_types=[])

    calls = []
    monkeypatch.setattr(scheduled_audits, "audit_page", lambda session, pid: calls.append(pid))

    with Session(db) as session:
        count = run_scheduled_audits(session)

    assert count == 0
    assert calls == []  # audit_page never called for a free-plan page


def test_a_failing_page_fetch_does_not_abort_the_whole_run(client, db, monkeypatch):
    headers1, page_id_1 = _setup_page(client, db, "sched5a@test.dev")
    headers2, page_id_2 = _setup_page(client, db, "sched5b@test.dev")
    _insert_audit(db, page_id_1, score=80, failed_check_types=[])
    _insert_audit(db, page_id_2, score=80, failed_check_types=[])

    good_new_audit = _new_audit_factory(score=50, failed_check_types=[])

    def fake_audit_page(session, pid):
        if pid == page_id_1:
            raise Exception("fetch failed")
        return good_new_audit(session, pid)

    monkeypatch.setattr(scheduled_audits, "audit_page", fake_audit_page)

    with Session(db) as session:
        count = run_scheduled_audits(session)

    assert count == 1  # page 2's score-drop alert still created despite page 1 failing
