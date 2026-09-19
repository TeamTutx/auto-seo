"""crawling, keyword discovery and search/AI visibility

Three features that all need background runs, so they share one job table:

- `sitejob` - progress for a crawl, a keyword discovery run, or a visibility
  check. The UI polls it.
- `page.discovered_via` + the four `index_*` columns - where a page came from
  and whether Google has it indexed. `index_source` records whether the answer
  came from Search Console ("gsc", free and authoritative) or a paid `site:`
  lookup ("serp", inference), because the two deserve different confidence.
- `keywordidea` - suggested keywords and which source proposed them. Unique per
  (site, keyword) so repeat discovery runs update rather than duplicate.
- `visibilitycheck` - one row per keyword per engine per run.

kind/status/source/engine are plain strings, not Postgres enums, for the reason
in the comment above Product in models.py.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("page", sa.Column("discovered_via", sa.String(), nullable=False, server_default="manual"))
    op.add_column("page", sa.Column("index_status", sa.String(), nullable=True))
    op.add_column("page", sa.Column("index_detail", sa.String(), nullable=True))
    op.add_column("page", sa.Column("index_source", sa.String(), nullable=True))
    op.add_column("page", sa.Column("index_checked_at", sa.DateTime(), nullable=True))

    op.create_table(
        "sitejob",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("site.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("credits_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_sitejob_site_id", "sitejob", ["site_id"])

    op.create_table(
        "keywordidea",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("site.id"), nullable=False),
        sa.Column("keyword", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("rationale", sa.String(), nullable=True),
        sa.Column("impressions", sa.Integer(), nullable=True),
        sa.Column("clicks", sa.Integer(), nullable=True),
        sa.Column("position", sa.Float(), nullable=True),
        sa.Column("targeted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("site_id", "keyword", name="uq_keywordidea_site_keyword"),
    )
    op.create_index("ix_keywordidea_site_id", "keywordidea", ["site_id"])

    op.create_table(
        "visibilitycheck",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("site.id"), nullable=False),
        sa.Column("keyword", sa.String(), nullable=False),
        sa.Column("engine", sa.String(), nullable=False),
        sa.Column("present", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_visibilitycheck_site_id", "visibilitycheck", ["site_id"])


def downgrade() -> None:
    op.drop_table("visibilitycheck")
    op.drop_table("keywordidea")
    op.drop_table("sitejob")
    with op.batch_alter_table("page") as batch:
        batch.drop_column("index_checked_at")
        batch.drop_column("index_source")
        batch.drop_column("index_detail")
        batch.drop_column("index_status")
        batch.drop_column("discovered_via")
