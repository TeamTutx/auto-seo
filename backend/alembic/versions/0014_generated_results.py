"""keep the results a credit paid for, and allow manually added keywords

`generatedresult` stores AI suggestions and competitor lookups. They used to
live in React state only, so refreshing the page threw away something the user
had just paid a credit for and seeing it again meant paying again. One row per
(page, kind, subject) - the newest replaces the last, because these answer "what
should I do now" rather than forming a history. `subject` is the keyword for
keyword-scoped results and "" for page-scoped ones; an empty string rather than
NULL, because Postgres treats NULLs as distinct in a unique constraint and would
happily store duplicates.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generatedresult",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("page.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False, server_default=""),
        sa.Column("payload", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("page_id", "kind", "subject", name="uq_generatedresult_page_kind_subject"),
    )
    op.create_index("ix_generatedresult_page_id", "generatedresult", ["page_id"])


def downgrade() -> None:
    op.drop_table("generatedresult")
