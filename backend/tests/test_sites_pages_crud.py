from sqlmodel import Session, select

from app.models import Audit, Check, KeywordRank, Page, Site
from tests.conftest import register_and_login


def test_update_site_domain_resets_verification(client, db):
    headers = register_and_login(client, "crud1@test.dev")
    site = client.post("/sites", json={"domain": "typo"}, headers=headers).json()

    resp = client.patch(f"/sites/{site['id']}", json={"domain": "fixed.com"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "fixed.com"
    assert body["verified"] is False


def test_delete_site_cascades_to_pages_audits_checks_and_keywords(client, db):
    headers = register_and_login(client, "crud2@test.dev")
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()
    page = client.post(
        f"/sites/{site['id']}/pages", json={"url": "https://example.com/"}, headers=headers
    ).json()

    # Insert audit/check/keyword rows directly - creating them for real would
    # need a live HTTP fetch or rank-provider call, which is out of scope here.
    with Session(db) as session:
        audit = Audit(page_id=page["id"], score=50)
        session.add(audit)
        session.commit()
        session.refresh(audit)
        session.add(Check(audit_id=audit.id, check_type="title_tag", status="pass", message="ok"))
        session.add(KeywordRank(page_id=page["id"], keyword="test", rank_position=1))
        session.commit()
        audit_id = audit.id

    resp = client.delete(f"/sites/{site['id']}", headers=headers)
    assert resp.status_code == 204

    with Session(db) as session:
        assert session.get(Site, site["id"]) is None
        assert session.get(Page, page["id"]) is None
        assert session.get(Audit, audit_id) is None
        assert session.exec(select(Check).where(Check.audit_id == audit_id)).all() == []
        assert session.exec(select(KeywordRank).where(KeywordRank.page_id == page["id"])).all() == []


def test_delete_page_removes_it_but_not_the_site(client):
    headers = register_and_login(client, "crud3@test.dev")
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()
    page = client.post(
        f"/sites/{site['id']}/pages", json={"url": "https://example.com/"}, headers=headers
    ).json()

    resp = client.delete(f"/pages/{page['id']}", headers=headers)
    assert resp.status_code == 204

    assert client.get(f"/pages/{page['id']}", headers=headers).status_code == 404
    assert client.get(f"/sites/{site['id']}", headers=headers).status_code == 200


def test_update_page_url_and_clear_target_keyword(client):
    headers = register_and_login(client, "crud4@test.dev")
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()
    page = client.post(
        f"/sites/{site['id']}/pages",
        json={"url": "https://example.com/old", "target_keyword": "old keyword"},
        headers=headers,
    ).json()

    resp = client.patch(
        f"/pages/{page['id']}",
        json={"url": "https://example.com/new", "target_keyword": ""},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["url"] == "https://example.com/new"
    assert body["target_keyword"] is None


def test_cannot_delete_another_users_site(client):
    headers_a = register_and_login(client, "crud5a@test.dev")
    headers_b = register_and_login(client, "crud5b@test.dev")
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers_a).json()

    resp = client.delete(f"/sites/{site['id']}", headers=headers_b)
    assert resp.status_code == 404
    assert client.get(f"/sites/{site['id']}", headers=headers_a).status_code == 200
