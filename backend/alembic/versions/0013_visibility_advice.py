"""keep the evidence behind a visibility reading, and store advice from it

`visibilitycheck.context` holds who actually won the search - the top organic
results, and the sources the AI Overview cited. The check already fetched them;
throwing them away meant any later "how do I fix this" had to buy the same
search again, and would have been advice about a *different* search than the one
on screen.

`visibilityadvice` stores the generated suggestions so re-reading them is free,
stamped with the reading they came from so the UI can say when they have gone
stale.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("visibilitycheck", sa.Column("context", sa.String(), nullable=True))

    op.create_table(
        "visibilityadvice",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("site.id"), nullable=False),
        sa.Column("keyword", sa.String(), nullable=False),
        sa.Column("diagnosis", sa.String(), nullable=False),
        sa.Column("actions", sa.String(), nullable=False),
        sa.Column("target_page_url", sa.String(), nullable=True),
        sa.Column("based_on_checked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_visibilityadvice_site_id", "visibilityadvice", ["site_id"])


def downgrade() -> None:
    op.drop_table("visibilityadvice")
    with op.batch_alter_table("visibilitycheck") as batch:
        batch.drop_column("context")
