"""where a site's changes get written, and the exact changes themselves

`sitewritetarget` is one row per site - a site's content lives in one place, and
two targets claiming the same site would mean writing a change twice or silently
picking one. **No row means manual**: the change is shown as a before/after to
copy, which is what every unconnected site gets.

`proposedchange` is one exact edit, with the value that was there before it, so
revert is a restore rather than a guess. Applying and reverting are history, so
unlike `generatedresult` these rows are never overwritten once applied.

Both use plain string columns for kind/status rather than Postgres enums - see
the block comment above Product in app/models.py, and migration 0007 for what a
mismatch between a Python enum name and a Postgres enum label cost last time.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sitewritetarget",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("site.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("config", sa.String(), nullable=False, server_default="{}"),
        sa.Column("secret_encrypted", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="untested"),
        sa.Column("status_detail", sa.String(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    # Unique, not just indexed: one target per site is the invariant, and the
    # database is the only place that can actually hold it under concurrency.
    op.create_index("ix_sitewritetarget_site_id", "sitewritetarget", ["site_id"], unique=True)

    op.create_table(
        "proposedchange",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("site.id"), nullable=False),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("page.id"), nullable=True),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False, server_default=""),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column("origin_ref", sa.String(), nullable=True),
        sa.Column("before", sa.String(), nullable=True),
        sa.Column("after", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="proposed"),
        sa.Column("target_kind", sa.String(), nullable=True),
        sa.Column("receipt", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("reverted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_proposedchange_site_id", "proposedchange", ["site_id"])
    op.create_index("ix_proposedchange_page_id", "proposedchange", ["page_id"])


def downgrade() -> None:
    op.drop_table("proposedchange")
    op.drop_index("ix_sitewritetarget_site_id", table_name="sitewritetarget")
    op.drop_table("sitewritetarget")
