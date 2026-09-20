import pytest
from sqlmodel import Session, select

import app.services.audit_runner as audit_runner
from app.models import Audit, Check
from tests.conftest import make_page, register_and_login

HTML = "<html><head><title>Hello</title></head><body><h1>Hi</h1><p>Some words here.</p></body></html>"


def _count(db, model):
    with Session(db) as session:
        return len(session.exec(select(model)).all())


def test_audit_and_checks_are_stored_together(client, db, monkeypatch):
    monkeypatch.setattr(audit_runner, "fetch_html", lambda url: HTML)
    headers = register_and_login(client, "atomic1@test.dev")
    page_id = make_page(client, headers)

    resp = client.post(f"/pages/{page_id}/audits", headers=headers)

    assert resp.status_code == 201
    assert len(resp.json()["checks"]) > 0
    assert _count(db, Audit) == 1
    assert _count(db, Check) == len(resp.json()["checks"])


def test_failed_check_insert_leaves_no_audit_behind(client, db, monkeypatch):
    monkeypatch.setattr(audit_runner, "fetch_html", lambda url: HTML)
    # simulates the Postgres enum-label failure that used to strand a score
    # with no checks: the check insert blows up at flush time.
    def boom(*args, **kwargs):
        raise RuntimeError("check insert failed")

    monkeypatch.setattr(audit_runner, "Check", boom)
    headers = register_and_login(client, "atomic2@test.dev")
    page_id = make_page(client, headers)

    with pytest.raises(RuntimeError):
        client.post(f"/pages/{page_id}/audits", headers=headers)

    assert _count(db, Audit) == 0


def test_an_audit_with_no_stored_checks_is_replaced_by_a_real_one(client, db, monkeypatch):
    monkeypatch.setattr(audit_runner, "fetch_html", lambda url: HTML)
    headers = register_and_login(client, "atomic3@test.dev")
    page_id = make_page(client, headers)
    # a legacy orphan: an audit that has a score but no stored checks
    with Session(db) as session:
        session.add(Audit(page_id=page_id, score=70))
        session.commit()

    resp = client.post(f"/pages/{page_id}/audits", headers=headers)

    assert resp.status_code == 201
    assert len(resp.json()["checks"]) > 0


def test_a_page_can_be_rescanned_immediately(client, db, monkeypatch):
    """Rescanning is free and deliberately unthrottled: you edit the page, come
    back, and want to know whether the check cleared. "Run full scan" also walks
    every page in turn, so any per-page gap made it fail against its own last
    run."""
    monkeypatch.setattr(audit_runner, "fetch_html", lambda url: HTML)
    headers = register_and_login(client, "atomic4@test.dev")
    page_id = make_page(client, headers)

    first = client.post(f"/pages/{page_id}/audits", headers=headers)
    second = client.post(f"/pages/{page_id}/audits", headers=headers)
    third = client.post(f"/pages/{page_id}/audits", headers=headers)

    assert [first.status_code, second.status_code, third.status_code] == [201, 201, 201]
    assert _count(db, Audit) == 3  # each one is a real, stored reading
