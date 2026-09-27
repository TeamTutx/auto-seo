"""Telling a customer something: in the app, and by email.

The rule these all circle is that the in-app alert is the durable record and the
email is a copy of it. A mail server being down must never cost someone the
message.
"""
import smtplib

import pytest
from sqlmodel import Session, select

from app.config import settings
from app.models import Alert, AlertType, User
from app.services import mailer, notifications
from tests.conftest import ADMIN_EMAIL, admin_headers, register_and_login  # noqa: F401

CUSTOMER = "customer@test.dev"


@pytest.fixture
def customer(client):
    register_and_login(client, CUSTOMER)
    return CUSTOMER


@pytest.fixture
def customer_id(db, customer):
    with Session(db) as session:
        return session.exec(select(User).where(User.email == customer)).first().id


@pytest.fixture
def smtp(monkeypatch):
    """A configured mail server that records what it was asked to send."""
    sent = []
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_from", "signal@test.dev")
    monkeypatch.setattr(mailer, "send", lambda to, subject, body: (sent.append((to, subject, body)), (True, f"Emailed {to}."))[1])
    return sent


# --- the message endpoint ---


def test_a_message_reaches_the_customers_alerts_and_their_inbox(client, admin_headers, customer_id, db, smtp):
    resp = client.post(
        f"/admin/users/{customer_id}/message",
        json={"subject": "Your account", "body": "Thanks for trying Signal."},
        headers=admin_headers,
    )

    assert resp.status_code == 201
    assert resp.json()["email_status"] == "sent"
    assert smtp == [(CUSTOMER, "Your account", "Thanks for trying Signal.")]
    with Session(db) as session:
        alert = session.exec(select(Alert).where(Alert.user_id == customer_id)).first()
        assert alert.alert_type == AlertType.message
        assert alert.subject == "Your account"
        assert alert.page_id is None, "a message about an account is not about a page"


def test_the_customer_can_read_it(client, admin_headers, customer_id, customer, smtp):
    client.post(
        f"/admin/users/{customer_id}/message",
        json={"subject": "Your account", "body": "Thanks for trying Signal."},
        headers=admin_headers,
    )
    theirs = register_and_login(client, CUSTOMER)

    alerts = client.get("/alerts", headers=theirs).json()

    assert [a["subject"] for a in alerts] == ["Your account"]
    assert alerts[0]["page_id"] is None and alerts[0]["site_id"] is None


def test_an_alert_with_no_page_is_not_dropped_by_the_join(client, admin_headers, customer_id, customer, smtp):
    """The listing used to inner-join Page, which would have silently hidden
    every account message rather than failing where anyone would notice."""
    client.post(
        f"/admin/users/{customer_id}/message",
        json={"subject": "One", "body": "First message."},
        headers=admin_headers,
    )
    theirs = register_and_login(client, CUSTOMER)

    assert len(client.get("/alerts", headers=theirs).json()) == 1


def test_a_message_can_be_marked_read_without_a_page(client, admin_headers, customer_id, customer, smtp):
    client.post(
        f"/admin/users/{customer_id}/message",
        json={"subject": "One", "body": "First message."},
        headers=admin_headers,
    )
    theirs = register_and_login(client, CUSTOMER)
    alert_id = client.get("/alerts", headers=theirs).json()[0]["id"]

    resp = client.post(f"/alerts/{alert_id}/read", headers=theirs)

    assert resp.status_code == 200 and resp.json()["read"] is True


def test_a_failed_email_still_delivers_the_message(client, admin_headers, customer_id, db, monkeypatch):
    """The worst possible outcome for this feature would be losing the message
    because a mail server was unreachable."""
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_from", "signal@test.dev")
    monkeypatch.setattr(mailer, "send", lambda *a: (False, "Could not reach smtp.test:587 - timed out"))

    resp = client.post(
        f"/admin/users/{customer_id}/message",
        json={"subject": "Your account", "body": "Still important."},
        headers=admin_headers,
    )

    assert resp.status_code == 201, "the message was delivered in-app; only the copy failed"
    assert resp.json()["email_status"] == "failed"
    assert "did not go" in resp.json()["detail"]
    with Session(db) as session:
        alert = session.exec(select(Alert).where(Alert.user_id == customer_id)).first()
        assert alert.message == "Still important."
        assert "timed out" in alert.email_error


def test_no_smtp_configured_says_so_rather_than_implying_delivery(client, admin_headers, customer_id, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")

    resp = client.post(
        f"/admin/users/{customer_id}/message",
        json={"subject": "Your account", "body": "Hello."},
        headers=admin_headers,
    )

    assert resp.json()["email_status"] == "disabled"
    assert "No SMTP server is configured" in resp.json()["detail"]


def test_email_can_be_skipped(client, admin_headers, customer_id, db, smtp):
    resp = client.post(
        f"/admin/users/{customer_id}/message",
        json={"subject": "Quiet note", "body": "No need to email this.", "send_email": False},
        headers=admin_headers,
    )

    assert resp.json()["email_status"] is None
    assert smtp == []


def test_only_an_admin_can_message_anyone(client, customer_id, customer):
    theirs = register_and_login(client, CUSTOMER)

    resp = client.post(
        f"/admin/users/{customer_id}/message",
        json={"subject": "Hello", "body": "From a customer."},
        headers=theirs,
    )

    assert resp.status_code == 403


# --- granting credits, with a notification ---


def test_granting_credits_tells_the_customer_their_new_balance(client, admin_headers, customer_id, db, smtp):
    client.post(
        f"/admin/users/{customer_id}/credits",
        json={"delta": 25, "note": "beta tester gift", "notify": True},
        headers=admin_headers,
    )

    to, subject, body = smtp[0]
    assert "25 credits added" in subject
    with Session(db) as session:
        user = session.get(User, customer_id)
        assert f"balance is now {user.credits_balance}" in body


def test_the_ledger_note_is_not_shown_to_the_customer(client, admin_headers, customer_id, smtp):
    """"beta tester gift" reads fine in an audit log and oddly in an email, so
    the customer's wording is written separately or generated."""
    client.post(
        f"/admin/users/{customer_id}/credits",
        json={"delta": 10, "note": "comped after the rank-check outage", "notify": True},
        headers=admin_headers,
    )

    _, _, body = smtp[0]
    assert "comped after the rank-check outage" not in body


def test_a_custom_message_is_appended(client, admin_headers, customer_id, smtp):
    client.post(
        f"/admin/users/{customer_id}/credits",
        json={"delta": 10, "note": "goodwill", "notify": True, "message": "Sorry about yesterday."},
        headers=admin_headers,
    )

    assert "Sorry about yesterday." in smtp[0][2]


def test_credits_are_not_announced_unless_asked(client, admin_headers, customer_id, db, smtp):
    """A correction the owner is making to their own books is not always news."""
    client.post(
        f"/admin/users/{customer_id}/credits",
        json={"delta": 5, "note": "ledger correction"},
        headers=admin_headers,
    )

    assert smtp == []
    with Session(db) as session:
        assert session.exec(select(Alert).where(Alert.user_id == customer_id)).all() == []


def test_a_failed_email_does_not_roll_back_the_credits(client, admin_headers, customer_id, db, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_from", "signal@test.dev")
    monkeypatch.setattr(mailer, "send", lambda *a: (False, "connection refused"))
    with Session(db) as session:
        before = session.get(User, customer_id).credits_balance

    resp = client.post(
        f"/admin/users/{customer_id}/credits",
        json={"delta": 30, "note": "gift", "notify": True},
        headers=admin_headers,
    )

    assert resp.status_code == 200
    with Session(db) as session:
        assert session.get(User, customer_id).credits_balance == before + 30


# --- the mailer itself ---


def test_the_mailer_is_off_until_it_has_somewhere_to_send(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "smtp_from", "a@b.test")
    assert mailer.enabled() is False

    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_from", "")
    assert mailer.enabled() is False


def test_a_rejected_password_explains_app_passwords(monkeypatch):
    """The single most common way this is misconfigured."""
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_from", "signal@test.dev")
    monkeypatch.setattr(settings, "smtp_username", "signal@test.dev")

    class _Refusing:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, *a): raise smtplib.SMTPAuthenticationError(535, b"nope")

    monkeypatch.setattr(mailer, "_connect", lambda: _Refusing())
    ok, detail = mailer.send("a@b.test", "s", "b")

    assert ok is False and "app-specific password" in detail


def test_an_unreachable_server_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_from", "signal@test.dev")

    def _boom():
        raise OSError("connection refused")

    monkeypatch.setattr(mailer, "_connect", _boom)
    ok, detail = mailer.send("a@b.test", "s", "b")

    assert ok is False and "Could not reach smtp.test" in detail


def test_the_message_is_plain_text_and_addressed_from_the_configured_sender(monkeypatch):
    monkeypatch.setattr(settings, "smtp_from", "signal@test.dev")
    monkeypatch.setattr(settings, "smtp_from_name", "Signal")

    message = mailer.build("someone@test.dev", "Subject here", "Body here.")

    assert message["From"] == "Signal <signal@test.dev>"
    assert message["To"] == "someone@test.dev"
    assert message.get_content_type() == "text/plain"
    assert message.get_content().strip() == "Body here."
