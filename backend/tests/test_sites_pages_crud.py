import pytest
from sqlmodel import Session, select

from app.models import Audit, Check, KeywordRank, Page, Site
from tests.conftest import register_and_login


def test_update_site_domain_resets_verification(client, db):
    headers = register_and_login(client, "crud1@test.dev")
    site = client.post("/sites", json={"domain": "old-domain.com"}, headers=headers).json()

    resp = client.patch(f"/sites/{site['id']}", json={"domain": "fixed.com"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "fixed.com"
    assert body["verified"] is False


def test_rejects_invalid_domain_on_create(client):
    headers = register_and_login(client, "crud6@test.dev")
    resp = client.post("/sites", json={"domain": "zepto"}, headers=headers)
    assert resp.status_code == 422


def test_normalizes_domain_on_create(client):
    headers = register_and_login(client, "crud7@test.dev")
    resp = client.post("/sites", json={"domain": "HTTPS://WWW.Example.COM/some/path"}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["domain"] == "example.com"


def test_verify_site_marks_verified_on_success(client, monkeypatch):
    import app.routers.sites as sites_router

    monkeypatch.setattr(sites_router, "verify_dns_txt", lambda domain, token: (True, "matched"))

    headers = register_and_login(client, "crud8@test.dev")
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()
    assert site["verified"] is False

    resp = client.post(f"/sites/{site['id']}/verify", json={"method": "dns_txt"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"verified": True, "message": "matched"}

    refreshed = client.get(f"/sites/{site['id']}", headers=headers).json()
    assert refreshed["verified"] is True
    assert refreshed["verification_method"] == "dns_txt"


def test_verify_site_leaves_unverified_on_failure(client, monkeypatch):
    import app.routers.sites as sites_router

    monkeypatch.setattr(sites_router, "verify_meta_tag", lambda domain, token: (False, "no matching tag"))

    headers = register_and_login(client, "crud9@test.dev")
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()

    resp = client.post(f"/sites/{site['id']}/verify", json={"method": "meta_tag"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"verified": False, "message": "no matching tag"}

    refreshed = client.get(f"/sites/{site['id']}", headers=headers).json()
    assert refreshed["verified"] is False


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


# --- URL normalisation on entry ---
#
# Search Console matches a page by exact URL, so a stray fragment or a capital
# in the host means its search data is silently unreachable - and "no data"
# looks identical to "this page gets no traffic".

@pytest.mark.parametrize("typed, stored", [
    ("example.com/pricing", "https://example.com/pricing"),          # no scheme typed
    ("https://EXAMPLE.com/Pricing", "https://example.com/Pricing"),  # host case only; paths are case-sensitive
    ("https://example.com/pricing#features", "https://example.com/pricing"),  # a fragment is a position, not a page
    ("  https://example.com/pricing  ", "https://example.com/pricing"),
    ("https://example.com", "https://example.com/"),                 # Search Console's form for a root
])
def test_a_hand_typed_page_url_is_tidied_before_it_is_stored(client, db, typed, stored):
    headers = register_and_login(client, f"norm{abs(hash(typed))}@test.dev")
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()

    page = client.post(f"/sites/{site['id']}/pages", json={"url": typed}, headers=headers).json()

    assert page["url"] == stored


def test_the_sites_own_trailing_slash_is_left_alone(client, db):
    """/about/ and /about are different canonical forms and Google records
    whichever one the site uses - so neither is rewritten into the other."""
    headers = register_and_login(client, "norm-slash@test.dev")
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()

    kept = client.post(f"/sites/{site['id']}/pages", json={"url": "https://example.com/about/"}, headers=headers)

    assert kept.json()["url"] == "https://example.com/about/"


@pytest.mark.parametrize("bad", [
    "", "   ",
    "ftp://example.com/a",
    "mailto:someone@example.com",
    "data:text/html,hi",
    # Without a real scheme check this became "https://javascript:alert(1)" - a
    # nonsense host that passed every later validation.
    "javascript:alert(1)",
    "https://not a host",
])
def test_something_that_is_not_a_page_url_is_refused(client, db, bad):
    headers = register_and_login(client, f"norm-bad{abs(hash(bad))}@test.dev")
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()

    assert client.post(f"/sites/{site['id']}/pages", json={"url": bad}, headers=headers).status_code == 422


def test_editing_a_page_url_normalises_it_too(client, db):
    headers = register_and_login(client, "norm-edit@test.dev")
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()
    page = client.post(f"/sites/{site['id']}/pages", json={"url": "https://example.com/a"}, headers=headers).json()

    updated = client.patch(f"/pages/{page['id']}", json={"url": "EXAMPLE.com/b#top"}, headers=headers)

    assert updated.json()["url"] == "https://example.com/b"
