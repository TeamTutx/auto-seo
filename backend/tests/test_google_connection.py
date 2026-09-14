from datetime import datetime, timedelta

from sqlmodel import Session

import app.services.google_connection as google_connection
from app.services.google_connection import (
    disconnect,
    get_connection,
    get_valid_access_token,
    save_connection,
)
from app.services.token_crypto import decrypt_token
from tests.conftest import register_and_login


def _register_user(client, email):
    register_and_login(client, email)
    from sqlmodel import select

    from app.models import User

    def _get(db):
        with Session(db) as session:
            return session.exec(select(User).where(User.email == email)).first()

    return _get


def test_save_connection_creates_a_new_row(client, db):
    get_user = _register_user(client, "gc1@test.dev")
    with Session(db) as session:
        user = get_user(db)
        conn = save_connection(
            session, user, {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600, "scope": "a b"}
        )
        assert decrypt_token(conn.access_token_encrypted) == "at-1"
        assert decrypt_token(conn.refresh_token_encrypted) == "rt-1"
        assert conn.scope == "a b"


def test_save_connection_without_a_refresh_token_on_first_connect_raises(client, db):
    get_user = _register_user(client, "gc2@test.dev")
    with Session(db) as session:
        user = get_user(db)
        try:
            save_connection(session, user, {"access_token": "at-1", "expires_in": 3600})
            assert False, "expected ValueError"
        except ValueError:
            pass


def test_save_connection_reuses_existing_refresh_token_when_google_omits_it(client, db):
    get_user = _register_user(client, "gc3@test.dev")
    with Session(db) as session:
        user = get_user(db)
        save_connection(session, user, {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600})

    with Session(db) as session:
        user = get_user(db)
        # a later token refresh/reconnect that doesn't return a refresh_token
        conn = save_connection(session, user, {"access_token": "at-2", "expires_in": 3600})
        assert decrypt_token(conn.access_token_encrypted) == "at-2"
        assert decrypt_token(conn.refresh_token_encrypted) == "rt-1"  # unchanged


def test_get_valid_access_token_returns_cached_token_when_not_near_expiry(client, db):
    get_user = _register_user(client, "gc4@test.dev")
    with Session(db) as session:
        user = get_user(db)
        save_connection(session, user, {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600})

    with Session(db) as session:
        connection = get_connection(session, get_user(db).id)
        token = get_valid_access_token(session, connection)
    assert token == "at-1"


def test_get_valid_access_token_refreshes_when_expired(client, db, monkeypatch):
    get_user = _register_user(client, "gc5@test.dev")
    with Session(db) as session:
        user = get_user(db)
        save_connection(session, user, {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600})

    # force it into the past so it's treated as expired
    with Session(db) as session:
        connection = get_connection(session, get_user(db).id)
        connection.token_expires_at = datetime.utcnow() - timedelta(minutes=5)
        session.add(connection)
        session.commit()

    monkeypatch.setattr(
        google_connection, "refresh_access_token", lambda refresh_token: {"access_token": "at-2", "expires_in": 3600}
    )

    with Session(db) as session:
        connection = get_connection(session, get_user(db).id)
        token = get_valid_access_token(session, connection)
    assert token == "at-2"

    with Session(db) as session:
        connection = get_connection(session, get_user(db).id)
        assert decrypt_token(connection.access_token_encrypted) == "at-2"
        assert connection.token_expires_at > datetime.utcnow()


def test_disconnect_removes_the_row(client, db):
    get_user = _register_user(client, "gc6@test.dev")
    with Session(db) as session:
        user = get_user(db)
        save_connection(session, user, {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600})

    with Session(db) as session:
        user_id = get_user(db).id
        assert disconnect(session, user_id) is True
        assert get_connection(session, user_id) is None


def test_disconnect_with_no_connection_returns_false(client, db):
    get_user = _register_user(client, "gc7@test.dev")
    with Session(db) as session:
        user_id = get_user(db).id
        assert disconnect(session, user_id) is False
