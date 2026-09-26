"""Compiling a suggestion into an exact change.

The interesting cases are all refusals: a field that edits prose, a page that is
already correct, and a page someone has edited since the change was built.
"""
import pytest
from sqlmodel import Session, select

from app.models import ChangeStatus, Page, ProposedChange, Site, User
from app.services import ai_suggestions, changes
from app.services.ai_providers import AIProvider, AIProviderError

HTML = """<html><head>
<title>Old Title</title>
<meta name="description" content="An old description that is long enough to be plausible.">
</head><body><h1>Hi</h1><img src="/cat.png"><img src="/dog.png" alt="A dog"></body></html>"""


class _Provider(AIProvider):
    name = "fake"

    def __init__(self, reply="New Title"):
        self.reply = reply

    def complete(self, system_prompt, user_prompt, max_tokens=300):
        return self.reply


@pytest.fixture
def page(db):
    with Session(db) as session:
        # A real owner row, not user_id=1: Postgres enforces the foreign key and
        # SQLite does not, so a hardcoded id passes locally and fails on the one
        # database that matters.
        owner = User(email="owner@test.dev", hashed_password="x")
        session.add(owner)
        session.commit()
        site = Site(user_id=owner.id, domain="example.com", verification_token="t", verified=True)
        session.add(site)
        session.commit()
        page = Page(site_id=site.id, url="https://example.com/about", target_keyword="widgets")
        session.add(page)
        session.commit()
        session.refresh(page)
        yield page


def _session(db):
    return Session(db)


# --- the deterministic pair: no model, no credit ---


def test_canonical_is_the_pages_own_url_and_costs_nothing(db, page):
    with _session(db) as session:
        compiled = changes.compile_field(session, page, "canonical_tag", HTML)
        session.commit()
        session.refresh(compiled.changes[0])

        assert compiled.credits == 0, "a deterministic answer has no model call to pay for"
        assert compiled.changes[0].after == "https://example.com/about"
        assert compiled.changes[0].before is None


def test_a_page_already_declaring_itself_canonical_has_nothing_to_change(db, page):
    html = HTML.replace("</head>", '<link rel="canonical" href="https://example.com/about"></head>')
    with _session(db) as session:
        with pytest.raises(changes.NothingToChange):
            changes.compile_field(session, page, "canonical_tag", html)


def test_robots_keeps_the_directives_that_are_not_blocking():
    """max-snippet and friends are the owner's choices, not mistakes - only the
    directives that stop the page being indexed come out."""
    assert changes._robots("noindex, follow, max-snippet:-1") == "follow, max-snippet:-1"


def test_a_robots_tag_that_is_only_blocking_becomes_index_follow():
    """Reverting to "no tag at all" would mean finding and deleting a tag; a
    value that says the same thing is something every target can simply set."""
    assert changes._robots("noindex, nofollow") == "index, follow"


def test_a_page_that_is_not_blocked_has_nothing_to_change(db, page):
    with _session(db) as session:
        with pytest.raises(changes.NothingToChange):
            changes.compile_field(session, page, "robots_meta_tag", HTML)


# --- the model-backed fields ---


def test_a_title_change_records_what_was_there_before(db, page, monkeypatch):
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: _Provider("Widgets That Work"))
    with _session(db) as session:
        compiled = changes.compile_field(session, page, "title_tag", HTML)
        session.commit()
        session.refresh(compiled.changes[0])

        assert compiled.credits == 1
        assert compiled.changes[0].before == "Old Title"
        assert compiled.changes[0].after == "Widgets That Work"


def test_structured_data_is_refused_rather_than_written_broken(db, page, monkeypatch):
    """Invalid JSON-LD is worse than none: Google reports it as an error against
    the page, so a reply that will not parse produces no change at all."""
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: _Provider("sorry, I can't do that"))
    with _session(db) as session:
        with pytest.raises(changes.NothingToChange):
            changes.compile_field(session, page, "structured_data", HTML)


def test_structured_data_is_reserialised_from_the_parsed_object(db, page, monkeypatch):
    monkeypatch.setattr(
        ai_suggestions, "get_ai_provider", lambda: _Provider('```json\n{"@type":"Article","headline":"Hi"}\n```')
    )
    with _session(db) as session:
        compiled = changes.compile_field(session, page, "structured_data", HTML)
        session.commit()
        session.refresh(compiled.changes[0])

        assert '"@context": "https://schema.org"' in compiled.changes[0].after
        assert "```" not in compiled.changes[0].after


def test_alt_text_is_one_credit_for_every_image_on_the_page(db, page, monkeypatch):
    """One model call produces them all, so billing per image would make a page
    with eight images eight times as expensive to fix for the same work."""
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: _Provider("1. A cat"))
    with _session(db) as session:
        compiled = changes.compile_field(session, page, "image_alt_text", HTML)
        session.commit()
        for change in compiled.changes:
            session.refresh(change)

        assert compiled.credits == 1
        # Only /cat.png is missing alt text; /dog.png already has some.
        assert [(c.subject, c.after) for c in compiled.changes] == [("/cat.png", "A cat")]


def test_a_vendor_failure_is_unsupported_not_a_crash(db, page, monkeypatch):
    class _Broken(AIProvider):
        name = "broken"

        def complete(self, *a, **k):
            raise AIProviderError("quota exhausted")

    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: _Broken())
    with _session(db) as session:
        with pytest.raises(changes.Unsupported, match="quota exhausted"):
            changes.compile_field(session, page, "title_tag", HTML)


# --- what is deliberately not applicable ---


@pytest.mark.parametrize("field", ["heading_structure", "readability", "content_length", "keyword_density", "link_analysis"])
def test_fields_that_edit_prose_are_refused_with_a_reason(db, page, field):
    """Not an oversight: setting a tag wrongly produces a wrong tag, while
    rewriting a paragraph wrongly produces a page that no longer says what the
    business meant. The UI shows the existing advice for these."""
    with _session(db) as session:
        with pytest.raises(changes.Unsupported) as exc:
            changes.compile_field(session, page, field, HTML)
    assert str(exc.value), "the refusal has to carry a sentence the UI can show"


# --- recompiling, and staleness ---


def test_recompiling_replaces_the_outstanding_proposal(db, page, monkeypatch):
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: _Provider("First"))
    with _session(db) as session:
        changes.compile_field(session, page, "title_tag", HTML)
        session.commit()
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: _Provider("Second"))
    with _session(db) as session:
        changes.compile_field(session, page, "title_tag", HTML)
        session.commit()

    with _session(db) as session:
        rows = session.exec(select(ProposedChange).where(ProposedChange.page_id == page.id)).all()
    assert len(rows) == 1 and rows[0].after == "Second"


def test_recompiling_never_overwrites_an_applied_change(db, page, monkeypatch):
    """An applied row is the record of an edit to a live site, including what was
    there before it. Overwriting it would lose the only note of both."""
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: _Provider("Applied one"))
    with _session(db) as session:
        compiled = changes.compile_field(session, page, "title_tag", HTML)
        session.commit()
        compiled.changes[0].status = ChangeStatus.applied.value
        session.add(compiled.changes[0])
        session.commit()

    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: _Provider("Newer one"))
    with _session(db) as session:
        changes.compile_field(session, page, "title_tag", HTML)
        session.commit()
        rows = session.exec(select(ProposedChange).where(ProposedChange.page_id == page.id)).all()

    assert sorted(r.after for r in rows) == ["Applied one", "Newer one"]


def test_a_change_is_stale_once_the_page_no_longer_holds_what_it_was_built_against(db, page, monkeypatch):
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: _Provider("New Title"))
    with _session(db) as session:
        change = changes.compile_field(session, page, "title_tag", HTML).changes[0]
        session.commit()

        assert changes.is_stale(change, HTML) is False
        assert changes.is_stale(change, HTML.replace("Old Title", "Something the owner typed")) is True


def test_whitespace_alone_does_not_make_a_change_stale(db, page, monkeypatch):
    """Rendered HTML re-wraps and re-indents between requests; treating that as
    an edit by the owner would refuse every apply on some sites."""
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: _Provider("New Title"))
    with _session(db) as session:
        change = changes.compile_field(session, page, "title_tag", HTML).changes[0]
        session.commit()
        session.refresh(change)

        rewrapped = HTML.replace("<title>Old Title</title>", "<title>\n  Old   Title\n</title>")
        assert changes.is_stale(change, rewrapped) is False


def test_an_applied_change_is_measured_against_what_it_put_there(db, page, monkeypatch):
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: _Provider("New Title"))
    with _session(db) as session:
        change = changes.compile_field(session, page, "title_tag", HTML).changes[0]
        change.status = ChangeStatus.applied.value
        session.commit()

        assert changes.is_stale(change, HTML) is True, "the page still shows the old title, so the write did not land"
        assert changes.is_stale(change, HTML.replace("Old Title", "New Title")) is False


# --- a fix that would not actually satisfy the check ---


def test_a_value_that_still_fails_its_own_check_is_flagged():
    """A model told to write 120-160 characters does not always write 120-160
    characters. Applying one of those spends a credit, changes the page, and
    leaves the audit still complaining - so the user is told before they apply,
    not after the next rescan."""
    assert changes.value_warning("meta_description", "x" * 113).startswith("This is 113 characters")
    assert changes.value_warning("title_tag", "Short") is not None


def test_a_value_inside_the_checks_range_is_not_flagged():
    assert changes.value_warning("meta_description", "x" * 130) is None
    assert changes.value_warning("title_tag", "x" * 45) is None


def test_fields_with_no_length_rule_are_never_flagged():
    assert changes.value_warning("canonical_tag", "https://example.com/about") is None
    assert changes.value_warning("image_alt_text", "A cat") is None


def test_the_warning_uses_the_audits_own_constants():
    """Hardcoding 120-160 here would let the two drift the first time someone
    tuned the audit."""
    from app.services import audit_engine

    just_under = "x" * (audit_engine.META_DESC_MIN_LEN - 1)
    exactly_min = "x" * audit_engine.META_DESC_MIN_LEN
    assert changes.value_warning("meta_description", just_under) is not None
    assert changes.value_warning("meta_description", exactly_min) is None
