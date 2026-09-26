"""Connecting a site, and applying changes through the API.

These cover the rules that have to hold whichever target is attached: a verified
site only, a credential tested before it is stored, a stale change refused, and
nothing charged for a write or an undo.
"""
import json

import pytest
from sqlmodel import Session, select

from app.models import AppliedFix, ChangeStatus, ProposedChange, Site, SiteWriteTarget, User
from app.routers import changes as changes_router
from app.services import ai_suggestions
from app.services.ai_providers import AIProvider
from app.services.write_targets import Receipt, TargetStatus, WriteTargetError
from tests.conftest import grant_credits, make_page, register_and_login

EMAIL = "fixer@test.dev"
HTML = '<html><head><title>Old Title</title></head><body><img src="/cat.png"></body></html>'


class _Provider(AIProvider):
    name = "fake"

    def __init__(self, reply="New Title"):
        self.reply = reply

    def complete(self, system_prompt, user_prompt, max_tokens=300):
        return self.reply


class _FakeTarget:
    """Stands in for a connected WordPress/GitHub so the API's own rules can be
    tested without either vendor's protocol in the way."""

    kind = "wordpress"
    writes_immediately = True

    def __init__(self, supports=("title_tag", "meta_description", "image_alt_text"), fail=None):
        self.supports = supports
        self.fail = fail
        self.wrote = []
        self.reverted = []

    def can_write(self, field):
        return field in self.supports

    def test(self):
        return TargetStatus(ok=True, detail="fine", capabilities=list(self.supports))

    def write(self, page_url, writes):
        if self.fail:
            raise WriteTargetError(self.fail)
        self.wrote.append((page_url, writes))
        return Receipt(ref="7", url="https://blog.test/wp-admin/post.php?post=7", detail="Updated 1 field.")

    def revert(self, page_url, writes, receipt):
        self.reverted.append((page_url, writes, receipt))
        return Receipt(ref="7", url=None, detail="Restored the previous value.")


@pytest.fixture
def headers(client):
    return register_and_login(client, EMAIL)


@pytest.fixture
def page_id(client, headers, db):
    page_id = make_page(client, headers, url="https://example.com/about")
    with Session(db) as session:
        site = session.exec(select(Site)).first()
        site.verified = True
        session.add(site)
        session.commit()
    return page_id


@pytest.fixture
def site_id(db):
    with Session(db) as session:
        return session.exec(select(Site)).first().id


@pytest.fixture(autouse=True)
def stub_the_page(monkeypatch):
    monkeypatch.setattr(changes_router, "fetch_html", lambda url: HTML)


@pytest.fixture
def ai(monkeypatch):
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: _Provider())


def _connect(db, site_id, kind="wordpress", config=None):
    """Attach a target row directly - the connect endpoint's own probe is tested
    separately, and every apply test would otherwise have to fake a vendor."""
    from app.services import token_crypto

    with Session(db) as session:
        session.add(SiteWriteTarget(
            site_id=site_id,
            kind=kind,
            config=json.dumps(config or {"base_url": "https://blog.test", "username": "bob",
                                         "capabilities": ["title_tag", "meta_description", "image_alt_text"]}),
            secret_encrypted=token_crypto.encrypt_token("app pass"),
            status="ok",
        ))
        session.commit()


# --- connecting ---


def test_an_unverified_site_cannot_be_connected(client, headers, db):
    """Attaching a write target to a domain the account has not proven it owns is
    the one mistake here that cannot be walked back."""
    make_page(client, headers, domain="notmine.com", url="https://notmine.com/")
    with Session(db) as session:
        site_id = session.exec(select(Site).where(Site.domain == "notmine.com")).first().id

    resp = client.put(
        f"/sites/{site_id}/write-target",
        json={"kind": "github", "secret": "ghp_" + "x" * 20, "repo": "acme/site"},
        headers=headers,
    )

    assert resp.status_code == 409
    assert "Verify you own this site" in resp.json()["detail"]


def test_a_credential_that_does_not_work_is_not_stored(client, headers, page_id, site_id, db, monkeypatch):
    monkeypatch.setattr(
        changes_router.write_targets, "GitHubTarget",
        lambda **kw: type("T", (), {"test": lambda self: TargetStatus(ok=False, detail="token is no good"),
                                    "supports": ()})(),
    )

    resp = client.put(
        f"/sites/{site_id}/write-target",
        json={"kind": "github", "secret": "ghp_" + "x" * 20, "repo": "acme/site"},
        headers=headers,
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "token is no good"
    with Session(db) as session:
        assert session.exec(select(SiteWriteTarget)).first() is None


def test_a_connection_never_returns_the_credential(client, headers, page_id, site_id, db):
    _connect(db, site_id)

    body = client.get(f"/sites/{site_id}/write-target", headers=headers).json()

    assert "secret" not in json.dumps(body).lower().replace("secret_detail", "")
    assert body["label"] == "blog.test"
    assert body["capabilities"] == ["title_tag", "meta_description", "image_alt_text"]
    assert body["writes_immediately"] is True


def test_an_unconnected_site_reports_null_not_an_error(client, headers, page_id, site_id):
    """No connection is the normal state for every site, not a failure."""
    resp = client.get(f"/sites/{site_id}/write-target", headers=headers)

    assert resp.status_code == 200
    assert resp.json() is None


def test_a_github_connection_says_its_writes_are_not_immediate(client, headers, page_id, site_id, db):
    _connect(db, site_id, kind="github", config={"repo": "acme/site", "branch": "main", "capabilities": ["title_tag"]})

    body = client.get(f"/sites/{site_id}/write-target", headers=headers).json()

    assert body["writes_immediately"] is False
    assert body["label"] == "acme/site"


def test_disconnecting_keeps_the_record_of_what_was_applied(client, headers, page_id, site_id, db, ai):
    """Those rows are the only note of what Signal changed on a real site, and
    what it was before."""
    _connect(db, site_id)
    client.post(f"/pages/{page_id}/changes/compile", json={"field": "title_tag"}, headers=headers)
    with Session(db) as session:
        row = session.exec(select(ProposedChange)).first()
        row.status = ChangeStatus.applied.value
        session.add(row)
        session.commit()

    assert client.delete(f"/sites/{site_id}/write-target", headers=headers).status_code == 204
    with Session(db) as session:
        assert session.exec(select(ProposedChange)).first().status == ChangeStatus.applied.value


# --- compiling, and what it costs ---


def test_compiling_a_deterministic_field_costs_nothing(client, headers, page_id, db):
    before = _balance(db)

    resp = client.post(f"/pages/{page_id}/changes/compile", json={"field": "canonical_tag"}, headers=headers)

    assert resp.status_code == 200
    assert resp.json()[0]["after"] == "https://example.com/about"
    assert _balance(db) == before, "no model ran, so there is nothing to pay for"


def test_compiling_a_generated_field_costs_one_credit(client, headers, page_id, db, ai):
    before = _balance(db)

    resp = client.post(f"/pages/{page_id}/changes/compile", json={"field": "title_tag"}, headers=headers)

    assert resp.status_code == 200
    assert _balance(db) == before - 1


def test_a_field_that_edits_prose_is_refused_with_a_reason(client, headers, page_id, db):
    before = _balance(db)

    resp = client.post(f"/pages/{page_id}/changes/compile", json={"field": "readability"}, headers=headers)

    assert resp.status_code == 422
    assert "drafts" in resp.json()["detail"]
    assert _balance(db) == before


def test_no_credits_is_refused_before_the_model_runs(client, headers, page_id, db, ai):
    grant_credits(db, EMAIL, 0)

    resp = client.post(f"/pages/{page_id}/changes/compile", json={"field": "title_tag"}, headers=headers)

    assert resp.status_code == 402


def test_a_compiled_change_survives_a_reload(client, headers, page_id, ai):
    """The rule from CLAUDE.md: a refresh must never lose what a credit bought."""
    client.post(f"/pages/{page_id}/changes/compile", json={"field": "title_tag"}, headers=headers)

    listed = client.get(f"/pages/{page_id}/changes", headers=headers).json()

    assert [c["field"] for c in listed] == ["title_tag"]
    assert listed[0]["before"] == "Old Title"


def test_another_account_cannot_read_a_pages_changes(client, headers, page_id, ai):
    client.post(f"/pages/{page_id}/changes/compile", json={"field": "title_tag"}, headers=headers)
    intruder = register_and_login(client, "someone-else@test.dev")

    assert client.get(f"/pages/{page_id}/changes", headers=intruder).status_code == 404


# --- applying ---


def test_applying_without_a_connection_says_where_to_connect_one(client, headers, page_id, ai):
    change = client.post(f"/pages/{page_id}/changes/compile", json={"field": "title_tag"}, headers=headers).json()[0]

    resp = client.post(f"/pages/{page_id}/changes/apply", json={"ids": [change["id"]]}, headers=headers)

    assert resp.status_code == 409
    assert "not connected" in resp.json()["detail"]


def test_applying_writes_to_the_target_and_records_the_receipt(client, headers, page_id, site_id, db, ai, monkeypatch):
    _connect(db, site_id)
    target = _FakeTarget()
    monkeypatch.setattr(changes_router.write_targets, "build", lambda row: target)
    change = client.post(f"/pages/{page_id}/changes/compile", json={"field": "title_tag"}, headers=headers).json()[0]
    before = _balance(db)

    resp = client.post(f"/pages/{page_id}/changes/apply", json={"ids": [change["id"]]}, headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] and body["receipt_url"].endswith("post=7")
    assert body["changes"][0]["status"] == "applied"
    assert target.wrote[0][0] == "https://example.com/about"
    assert _balance(db) == before, "applying is free - the credit paid for the compile"


def test_applying_starts_the_verification_loop_that_already_exists(client, headers, page_id, site_id, db, ai, monkeypatch):
    """Phase D's AppliedFix machinery checks on the next audit whether the check
    now passes, and raises fix_verified. Auto-applied changes reuse it."""
    _connect(db, site_id)
    monkeypatch.setattr(changes_router.write_targets, "build", lambda row: _FakeTarget())
    change = client.post(f"/pages/{page_id}/changes/compile", json={"field": "title_tag"}, headers=headers).json()[0]

    client.post(f"/pages/{page_id}/changes/apply", json={"ids": [change["id"]]}, headers=headers)

    with Session(db) as session:
        fixes = session.exec(select(AppliedFix)).all()
    assert [(f.check_type, f.resolved) for f in fixes] == [("title_tag", False)]


def test_a_field_the_connection_cannot_write_is_refused_before_any_call(client, headers, page_id, site_id, db, monkeypatch):
    _connect(db, site_id)
    target = _FakeTarget(supports=("image_alt_text",))
    monkeypatch.setattr(changes_router.write_targets, "build", lambda row: target)
    change = client.post(f"/pages/{page_id}/changes/compile", json={"field": "canonical_tag"}, headers=headers).json()[0]

    resp = client.post(f"/pages/{page_id}/changes/apply", json={"ids": [change["id"]]}, headers=headers)

    assert resp.status_code == 422
    assert "Copy the value in instead" in resp.json()["detail"]
    assert target.wrote == []


def test_a_page_edited_since_the_change_was_built_is_refused(client, headers, page_id, site_id, db, ai, monkeypatch):
    """Applying would overwrite the owner's edit with a suggestion written for the
    old page."""
    _connect(db, site_id)
    target = _FakeTarget()
    monkeypatch.setattr(changes_router.write_targets, "build", lambda row: target)
    change = client.post(f"/pages/{page_id}/changes/compile", json={"field": "title_tag"}, headers=headers).json()[0]
    monkeypatch.setattr(changes_router, "fetch_html", lambda url: HTML.replace("Old Title", "Something they typed"))

    resp = client.post(f"/pages/{page_id}/changes/apply", json={"ids": [change["id"]]}, headers=headers)

    assert resp.status_code == 409
    assert "edited it since" in resp.json()["detail"]
    assert target.wrote == []


def test_a_failed_write_is_recorded_on_the_change(client, headers, page_id, site_id, db, ai, monkeypatch):
    _connect(db, site_id)
    monkeypatch.setattr(changes_router.write_targets, "build", lambda row: _FakeTarget(fail="WordPress said no"))
    change = client.post(f"/pages/{page_id}/changes/compile", json={"field": "title_tag"}, headers=headers).json()[0]

    resp = client.post(f"/pages/{page_id}/changes/apply", json={"ids": [change["id"]]}, headers=headers)

    assert resp.status_code == 502
    with Session(db) as session:
        row = session.get(ProposedChange, change["id"])
        assert row.status == ChangeStatus.failed.value
        assert row.error == "WordPress said no"


def test_applying_something_already_applied_is_refused(client, headers, page_id, site_id, db, ai, monkeypatch):
    _connect(db, site_id)
    monkeypatch.setattr(changes_router.write_targets, "build", lambda row: _FakeTarget())
    change = client.post(f"/pages/{page_id}/changes/compile", json={"field": "title_tag"}, headers=headers).json()[0]
    client.post(f"/pages/{page_id}/changes/apply", json={"ids": [change["id"]]}, headers=headers)

    resp = client.post(f"/pages/{page_id}/changes/apply", json={"ids": [change["id"]]}, headers=headers)

    assert resp.status_code == 409


# --- undo ---


def test_reverting_writes_the_old_value_back_and_costs_nothing(client, headers, page_id, site_id, db, ai, monkeypatch):
    _connect(db, site_id)
    target = _FakeTarget()
    monkeypatch.setattr(changes_router.write_targets, "build", lambda row: target)
    change = client.post(f"/pages/{page_id}/changes/compile", json={"field": "title_tag"}, headers=headers).json()[0]
    client.post(f"/pages/{page_id}/changes/apply", json={"ids": [change["id"]]}, headers=headers)
    before = _balance(db)

    resp = client.post(f"/pages/{page_id}/changes/revert", json={"ids": [change["id"]]}, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["changes"][0]["status"] == "reverted"
    assert target.reverted[0][1][0].value == "Old Title", "the value to write back is what was there before"
    assert _balance(db) == before, "charging for undo is indefensible"


def test_reverting_removes_the_pending_verification(client, headers, page_id, site_id, db, ai, monkeypatch):
    """Otherwise the next audit would announce a fix as verified when nothing is
    applied any more."""
    _connect(db, site_id)
    monkeypatch.setattr(changes_router.write_targets, "build", lambda row: _FakeTarget())
    change = client.post(f"/pages/{page_id}/changes/compile", json={"field": "title_tag"}, headers=headers).json()[0]
    client.post(f"/pages/{page_id}/changes/apply", json={"ids": [change["id"]]}, headers=headers)

    client.post(f"/pages/{page_id}/changes/revert", json={"ids": [change["id"]]}, headers=headers)

    with Session(db) as session:
        assert session.exec(select(AppliedFix)).all() == []


def test_a_change_that_is_live_cannot_be_discarded(client, headers, page_id, site_id, db, ai, monkeypatch):
    _connect(db, site_id)
    monkeypatch.setattr(changes_router.write_targets, "build", lambda row: _FakeTarget())
    change = client.post(f"/pages/{page_id}/changes/compile", json={"field": "title_tag"}, headers=headers).json()[0]
    client.post(f"/pages/{page_id}/changes/apply", json={"ids": [change["id"]]}, headers=headers)

    resp = client.delete(f"/pages/{page_id}/changes/{change['id']}", headers=headers)

    assert resp.status_code == 409
    assert "Revert it instead" in resp.json()["detail"]


def test_a_proposal_can_be_discarded(client, headers, page_id, ai):
    change = client.post(f"/pages/{page_id}/changes/compile", json={"field": "title_tag"}, headers=headers).json()[0]

    assert client.delete(f"/pages/{page_id}/changes/{change['id']}", headers=headers).status_code == 204
    assert client.get(f"/pages/{page_id}/changes", headers=headers).json() == []


def _balance(db):
    with Session(db) as session:
        return session.exec(select(User).where(User.email == EMAIL)).first().credits_balance
