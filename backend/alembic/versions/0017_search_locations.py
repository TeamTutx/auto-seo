"""make the country list editable, and record where a search was measured

Three things, all about the same gap: Signal could measure a search in one of
five countries, the five were a hardcoded array in the frontend bundle, and
nothing outside rank tracking knew about countries at all.

- `searchlocation` is the list, as rows the owner edits in /admin. Seeded with
  exactly the five that were hardcoded, so nothing changes on deploy.
- `site.default_location_code` is a site's home market. Visibility runs used the
  service's India default and never passed anything, so every reading in the
  product was Indian and nothing said so.
- `visibilitycheck.location_code` records where each reading was taken. Existing
  rows are backfilled to 2356, which is genuinely where they were measured.

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

# The list as frontend/lib/types.ts hardcoded it, in the same order.
SEEDED = [
    (2356, "India", 10),
    (2840, "United States", 20),
    (2826, "United Kingdom", 30),
    (2124, "Canada", 40),
    (2036, "Australia", 50),
]

INDIA = 2356


def upgrade() -> None:
    locations = op.create_table(
        "searchlocation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_searchlocation_code"),
    )
    op.create_index("ix_searchlocation_code", "searchlocation", ["code"])
    op.bulk_insert(
        locations,
        [{"code": code, "label": label, "active": True, "sort_order": order} for code, label, order in SEEDED],
    )

    # server_default on both: existing rows need a value, and the model's own
    # default only applies to rows Python creates.
    op.add_column(
        "site",
        sa.Column("default_location_code", sa.Integer(), nullable=False, server_default=str(INDIA)),
    )
    op.add_column(
        "visibilitycheck",
        sa.Column("location_code", sa.Integer(), nullable=False, server_default=str(INDIA)),
    )


def downgrade() -> None:
    op.drop_column("visibilitycheck", "location_code")
    op.drop_column("site", "default_location_code")
    op.drop_index("ix_searchlocation_code", table_name="searchlocation")
    op.drop_table("searchlocation")
