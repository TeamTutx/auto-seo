from sqlmodel import Session

from app.models import Alert, AlertType
from tests.conftest import make_page, register_and_login


def test_list_and_mark_alert_read(client, db):
    headers = register_and_login(client, "alert1@test.dev")
    page_id = make_page(client, headers)
    user_id = client.get("/auth/me", headers=headers).json()["id"]

    with Session(db) as session:
        alert = Alert(user_id=user_id, page_id=page_id, alert_type=AlertType.score_drop, message="dropped")
        session.add(alert)
        session.commit()
        session.refresh(alert)
        alert_id = alert.id

    listing = client.get("/alerts", headers=headers).json()
    assert len(listing) == 1
    assert listing[0]["read"] is False

    resp = client.post(f"/alerts/{alert_id}/read", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["read"] is True

    listing = client.get("/alerts", headers=headers).json()
    assert listing[0]["read"] is True


def test_cannot_read_another_users_alert(client, db):
    headers_a = register_and_login(client, "alert2a@test.dev")
    headers_b = register_and_login(client, "alert2b@test.dev")
    page_id = make_page(client, headers_a)
    user_a_id = client.get("/auth/me", headers=headers_a).json()["id"]

    with Session(db) as session:
        alert = Alert(user_id=user_a_id, page_id=page_id, alert_type=AlertType.new_fail, message="new fail")
        session.add(alert)
        session.commit()
        session.refresh(alert)
        alert_id = alert.id

    resp = client.post(f"/alerts/{alert_id}/read", headers=headers_b)
    assert resp.status_code == 404
