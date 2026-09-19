from datetime import datetime, timedelta

from sqlmodel import Session

from app.models import Audit, Check, CheckStatus
from tests.conftest import register_and_login


def _make_site_and_page(client, headers, domain="example.com"):
    site = client.post("/sites", json={"domain": domain}, headers=headers).json()
    page = client.post(f"/sites/{site['id']}/pages", json={"url": f"https://{domain}/"}, headers=headers).json()
    return site["id"], page["id"]


def _insert_audit(db, page_id, checks, minutes_ago=0):
    with Session(db) as session:
        audit = Audit(page_id=page_id, score=50, created_at=datetime.utcnow() - timedelta(minutes=minutes_ago))
        session.add(audit)
        session.commit()
        session.refresh(audit)
        for check_type, status_, message in checks:
            session.add(Check(audit_id=audit.id, check_type=check_type, status=status_, message=message))
        session.commit()


def test_apply_endpoint_creates_an_applied_fix(client, db):
    headers = register_and_login(client, "apply1@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_audit(db, page_id, [("meta_description", CheckStatus.fail, "Missing meta description.")])

    resp = client.post(
        f"/pages/{page_id}/opportunities/apply",
        json={"type": "audit_fail", "check_type": "meta_description"},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "audit_fail"
    assert body["check_type"] == "meta_description"
    assert body["resolved"] is False


def test_apply_endpoint_requires_check_type_for_audit_opportunities(client, db):
    headers = register_and_login(client, "apply2@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)

    resp = client.post(f"/pages/{page_id}/opportunities/apply", json={"type": "audit_fail"}, headers=headers)
    assert resp.status_code == 422


def test_apply_endpoint_requires_keyword_for_keyword_opportunities(client, db):
    headers = register_and_login(client, "apply3@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)

    resp = client.post(f"/pages/{page_id}/opportunities/apply", json={"type": "keyword_not_found"}, headers=headers)
    assert resp.status_code == 422


def test_applied_opportunity_shows_applied_true_until_resolved(client, db):
    headers = register_and_login(client, "apply4@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    _insert_audit(db, page_id, [("meta_description", CheckStatus.fail, "Missing meta description.")])

    before = client.get(f"/sites/{site_id}/opportunities", headers=headers).json()
    assert before[0]["applied"] is False

    client.post(
        f"/pages/{page_id}/opportunities/apply",
        json={"type": "audit_fail", "check_type": "meta_description"},
        headers=headers,
    )

    after = client.get(f"/sites/{site_id}/opportunities", headers=headers).json()
    assert after[0]["applied"] is True


def test_rescan_resolves_the_applied_fix_and_opportunity_disappears(client, db, monkeypatch):
    import app.services.audit_runner as audit_runner

    headers = register_and_login(client, "apply5@test.dev")
    site_id, page_id = _make_site_and_page(client, headers)
    # Older than RESCAN_THROTTLE, as a real baseline would be by the time
    # someone has edited their page and come back to verify the fix.
    _insert_audit(
        db, page_id, [("meta_description", CheckStatus.fail, "Missing meta description.")], minutes_ago=10
    )

    client.post(
        f"/pages/{page_id}/opportunities/apply",
        json={"type": "audit_fail", "check_type": "meta_description"},
        headers=headers,
    )

    FIXED_HTML = (
        "<html><head><title>A perfectly fine 30-60 char title here</title>"
        '<meta name="description" content="'
        + ("A" * 130)
        + '"></head><body>'
        + ("word " * 350)
        + "<h1>Heading</h1></body></html>"
    )
    monkeypatch.setattr(audit_runner, "fetch_html", lambda url: FIXED_HTML)

    resp = client.post(f"/pages/{page_id}/audits", headers=headers)
    assert resp.status_code == 201

    opportunities = client.get(f"/sites/{site_id}/opportunities", headers=headers).json()
    assert all(o["check_type"] != "meta_description" for o in opportunities)

    alerts = client.get("/alerts", headers=headers).json()
    assert any(a["alert_type"] == "fix_verified" for a in alerts)
