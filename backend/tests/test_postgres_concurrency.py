"""Real concurrent transactions - only meaningful on Postgres (row locks, unique
constraints under contention). Skipped on the default in-memory SQLite run; use
TEST_DATABASE_URL=postgresql://... to run it (see tests/conftest.py)."""
import threading

import pytest
from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import CreditTransaction, Payment, PaymentKind, User
from app.services.billing import record_payment
from app.services.credits import deduct_credit
from tests.conftest import TEST_DATABASE_URL, get_user, register_and_login

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="needs a real Postgres (set TEST_DATABASE_URL)")


def _run_in_threads(n, work):
    barrier = threading.Barrier(n)
    results = [None] * n

    def runner(i):
        barrier.wait()  # release everyone at once to maximise contention
        try:
            results[i] = ("ok", work(i))
        except Exception as exc:  # noqa: BLE001 - we're classifying outcomes
            results[i] = ("err", exc)

    threads = [threading.Thread(target=runner, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_parallel_spends_never_overdraw_and_each_success_is_ledgered(client, db):
    register_and_login(client, "race1@test.dev")
    user_id = get_user(db, "race1@test.dev").id  # balance 3

    def spend(_):
        with Session(db) as session:
            deduct_credit(session, session.get(User, user_id), "ai_title_tag")

    results = _run_in_threads(12, spend)

    ok = [r for r in results if r[0] == "ok"]
    refused = [r for r in results if r[0] == "err"]
    assert len(ok) == 3 and len(refused) == 9
    assert all(isinstance(r[1], HTTPException) and r[1].status_code == 402 for r in refused)
    with Session(db) as session:
        assert session.get(User, user_id).credits_balance == 0
        usage = session.exec(select(CreditTransaction).where(CreditTransaction.reason == "usage")).all()
        assert len(usage) == 3
        total = session.exec(select(CreditTransaction).where(CreditTransaction.user_id == user_id)).all()
        assert sum(t.delta for t in total) == 0  # signup +3, usage -3


def test_parallel_deliveries_of_one_payment_grant_credits_exactly_once(client, db):
    register_and_login(client, "race2@test.dev")
    user_id = get_user(db, "race2@test.dev").id

    def deliver(_):
        with Session(db) as session:
            payment, created = record_payment(
                session, user=session.get(User, user_id), amount_cents=900, kind=PaymentKind.credit_pack,
                provider="dodo", provider_ref="pay_parallel", credits=50,
            )
            session.commit()
            return created

    results = _run_in_threads(10, deliver)

    assert all(r[0] == "ok" for r in results), [r for r in results if r[0] == "err"]
    assert sum(1 for r in results if r[1] is True) == 1  # exactly one delivery "won"
    with Session(db) as session:
        assert len(session.exec(select(Payment)).all()) == 1
        assert session.get(User, user_id).credits_balance == 53
