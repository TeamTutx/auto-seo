import pytest
from sqlmodel import Session, select

import app.services.keyword_rank_runner as keyword_rank_runner
from app.models import CreditReason, CreditTransaction
from app.services.credits import InsufficientCredits, apply_credit_delta, deduct_credit
from app.services.rank_providers.base import RankProvider
from tests.conftest import get_user, make_page, register_and_login


def _ledger(db, email):
    user = get_user(db, email)
    with Session(db) as session:
        return user, session.exec(
            select(CreditTransaction).where(CreditTransaction.user_id == user.id).order_by(CreditTransaction.id)
        ).all()


def test_signup_is_recorded_in_the_ledger(client, db):
    register_and_login(client, "ledger1@test.dev")

    user, rows = _ledger(db, "ledger1@test.dev")

    assert [(r.delta, r.balance_after, r.reason) for r in rows] == [(3, 3, "signup")]
    assert sum(r.delta for r in rows) == user.credits_balance


def test_apply_credit_delta_updates_balance_and_writes_a_matching_row(client, db):
    register_and_login(client, "ledger2@test.dev")
    user = get_user(db, "ledger2@test.dev")

    with Session(db) as session:
        new_balance = apply_credit_delta(session, user.id, 7, CreditReason.admin, note="goodwill", actor_id=user.id)
        session.commit()

    assert new_balance == 10
    user, rows = _ledger(db, "ledger2@test.dev")
    assert user.credits_balance == 10
    assert (rows[-1].delta, rows[-1].balance_after, rows[-1].reason, rows[-1].note) == (7, 10, "admin", "goodwill")
    assert sum(r.delta for r in rows) == user.credits_balance


def test_the_balance_can_never_go_negative(client, db):
    register_and_login(client, "ledger3@test.dev")
    user = get_user(db, "ledger3@test.dev")

    with Session(db) as session:
        with pytest.raises(InsufficientCredits):
            apply_credit_delta(session, user.id, -4, CreditReason.usage)
        session.rollback()

    user, rows = _ledger(db, "ledger3@test.dev")
    assert user.credits_balance == 3  # untouched
    assert len(rows) == 1  # and nothing was logged for the refused change


def test_a_zero_delta_is_rejected(client, db):
    register_and_login(client, "ledger4@test.dev")
    user = get_user(db, "ledger4@test.dev")
    with Session(db) as session:
        with pytest.raises(ValueError):
            apply_credit_delta(session, user.id, 0, CreditReason.admin)


def test_deduct_credit_records_what_it_was_spent_on(client, db):
    register_and_login(client, "ledger5@test.dev")
    user = get_user(db, "ledger5@test.dev")

    with Session(db) as session:
        deduct_credit(session, session.get(type(user), user.id), "keyword_check")

    user, rows = _ledger(db, "ledger5@test.dev")
    assert user.credits_balance == 2
    assert (rows[-1].delta, rows[-1].reason, rows[-1].ref) == (-1, "usage", "keyword_check")


def test_spending_the_last_credit_twice_is_refused_not_overdrawn(client, db):
    """The race the old read-modify-write allowed: two requests both pass the
    balance check, then both spend. The second spend must now fail cleanly."""
    from fastapi import HTTPException

    register_and_login(client, "ledger6@test.dev")
    user = get_user(db, "ledger6@test.dev")
    with Session(db) as session:
        apply_credit_delta(session, user.id, -2, CreditReason.usage)  # leave exactly 1
        session.commit()

    with Session(db) as first, Session(db) as second:
        first_user, second_user = first.get(type(user), user.id), second.get(type(user), user.id)
        # both sessions saw balance == 1 before either spent
        assert first_user.credits_balance == second_user.credits_balance == 1
        deduct_credit(first, first_user, "ai_title_tag")
        with pytest.raises(HTTPException) as exc:
            deduct_credit(second, second_user, "ai_title_tag")
        assert exc.value.status_code == 402

    user, rows = _ledger(db, "ledger6@test.dev")
    assert user.credits_balance == 0
    assert sum(r.delta for r in rows) == 0 + 3 - 3  # ledger still sums to the balance


class _Provider(RankProvider):
    name = "fake"

    def fetch_serp(self, *a, **k):
        return []

    def fetch_rank(self, *a, **k):
        return 4


def test_a_real_keyword_check_shows_up_in_the_ledger(client, db, monkeypatch):
    monkeypatch.setattr(keyword_rank_runner, "get_rank_provider", lambda: _Provider())
    headers = register_and_login(client, "ledger7@test.dev")
    page_id = make_page(client, headers)

    assert client.post(f"/pages/{page_id}/keywords", json={"keyword": "x"}, headers=headers).status_code == 201

    user, rows = _ledger(db, "ledger7@test.dev")
    assert (rows[-1].reason, rows[-1].ref, rows[-1].delta) == ("usage", "keyword_check", -1)
    assert sum(r.delta for r in rows) == user.credits_balance == 2
