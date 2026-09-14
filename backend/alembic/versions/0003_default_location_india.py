"""default keywordrank.location_code to India (2356) instead of US (2840)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-14

App-level code always passes location_code explicitly, so this doesn't
change runtime behavior - it's just keeping the column default truthful
for anyone doing a raw insert or introspecting the schema.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite has no ALTER COLUMN; batch mode recreates the table under the
    # hood so this works on both SQLite (dev) and Postgres (prod).
    with op.batch_alter_table("keywordrank") as batch_op:
        batch_op.alter_column("location_code", server_default="2356")


def downgrade() -> None:
    with op.batch_alter_table("keywordrank") as batch_op:
        batch_op.alter_column("location_code", server_default="2840")
