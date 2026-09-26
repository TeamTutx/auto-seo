"""Deleting a site must not leave rows pointing at it.

This is a structural test on purpose. Postgres enforces the foreign keys and
refuses the delete; SQLite - dev, and the whole pytest suite - does not enforce
them by default, so a table missing from cascade_delete looks perfectly fine
locally and fails only in production, on a user pressing Delete. That is what had
happened: the function covered audits, checks and keyword ranks and none of the
seven tables added by later phases.

So rather than listing tables (which is the thing that went stale), this asks the
metadata which tables point at a site or a page, and fails if any of them still
has rows afterwards. A new table with a site_id gets caught here.
"""
from datetime import datetime

import pytest
from sqlmodel import Session, SQLModel, select

from app.models import (
    Alert,
    AlertType,
    AppliedFix,
    Audit,
    Check,
    CheckStatus,
    GeneratedResult,
    KeywordIdea,
    KeywordRank,
    OpportunityType,
    Page,
    ProposedChange,
    Site,
    SiteJob,
    SiteWriteTarget,
    User,
    VisibilityAdvice,
    VisibilityCheck,
)
from app.services.cascade_delete import delete_site


def _tables_pointing_at_sites_or_pages():
    """Every table reachable from `site` or `page` by foreign keys, followed
    transitively - `check` points at `audit`, which points at `page`, and it has
    to be deleted for exactly the same reason as the direct children."""
    reachable = {"site", "page"}
    while True:
        found = {
            table.name
            for table in SQLModel.metadata.sorted_tables
            for column in table.columns
            for fk in column.foreign_keys
            if fk.column.table.name in reachable
        }
        if found <= reachable:
            return reachable - {"site"}
        reachable |= found


def test_the_fixture_below_covers_every_table_that_points_at_a_site_or_page():
    """If this fails, a table was added without a row in `populate` - and probably
    without a line in cascade_delete either."""
    assert _tables_pointing_at_sites_or_pages() == set(_POPULATED)


@pytest.fixture
def populated(db):
    with Session(db) as session:
        user = User(email="owner@test.dev", hashed_password="x")
        session.add(user)
        session.commit()

        site = Site(user_id=user.id, domain="example.com", verification_token="t")
        session.add(site)
        session.commit()
        page = Page(site_id=site.id, url="https://example.com/")
        session.add(page)
        session.commit()
        audit = Audit(page_id=page.id, score=50)
        session.add(audit)
        session.commit()

        session.add_all([
            Check(audit_id=audit.id, check_type="title_tag", status=CheckStatus.fail, message="m"),
            KeywordRank(page_id=page.id, keyword="widgets"),
            AppliedFix(page_id=page.id, opportunity_type=OpportunityType.audit_fail, check_type="title_tag"),
            Alert(user_id=user.id, page_id=page.id, alert_type=AlertType.new_fail, message="m"),
            GeneratedResult(page_id=page.id, kind="title_tag", payload="{}"),
            ProposedChange(site_id=site.id, page_id=page.id, field="title_tag", origin="audit_check", after="x"),
            # A change with no page: the advice said to publish something new.
            ProposedChange(site_id=site.id, page_id=None, field="title_tag", origin="visibility_advice", after="y"),
            SiteWriteTarget(site_id=site.id, kind="github", secret_encrypted="enc"),
            KeywordIdea(site_id=site.id, keyword="widgets", source="ai"),
            VisibilityCheck(site_id=site.id, keyword="widgets", engine="google"),
            VisibilityAdvice(site_id=site.id, keyword="widgets", diagnosis="d", actions="[]"),
            SiteJob(site_id=site.id, kind="crawl", created_at=datetime.utcnow()),
        ])
        session.commit()
        return site.id


_POPULATED = {
    "page", "audit", "check", "keywordrank", "appliedfix", "alert", "generatedresult",
    "proposedchange", "sitewritetarget", "keywordidea", "visibilitycheck", "visibilityadvice",
    "sitejob",
}


def test_deleting_a_site_leaves_nothing_behind(db, populated):
    with Session(db) as session:
        delete_site(session, populated)

    with Session(db) as session:
        leftovers = {
            name: session.exec(select(SQLModel.metadata.tables[name])).all()
            for name in _tables_pointing_at_sites_or_pages()
        }
    assert {name: rows for name, rows in leftovers.items() if rows} == {}
    with Session(db) as session:
        assert session.get(Site, populated) is None


def test_the_owner_survives_their_sites_deletion(db, populated):
    with Session(db) as session:
        delete_site(session, populated)

    with Session(db) as session:
        assert session.exec(select(User)).all(), "deleting a site must not delete the account"
