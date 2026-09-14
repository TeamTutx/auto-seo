"""add applied_fix table, extend alerttype with fix_verified

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

opportunity_type = sa.Enum(
    "audit_fail", "audit_warning", "keyword_not_found", "keyword_low_rank", "keyword_rank_drop",
    name="opportunitytype",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE alerttype ADD VALUE IF NOT EXISTS 'fix_verified'")

    op.create_table(
        "appliedfix",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("page.id"), nullable=False),
        sa.Column("opportunity_type", opportunity_type, nullable=False),
        sa.Column("check_type", sa.String(), nullable=True),
        sa.Column("keyword", sa.String(), nullable=True),
        sa.Column("baseline_score", sa.Integer(), nullable=True),
        sa.Column("baseline_rank", sa.Integer(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_appliedfix_page_id", "appliedfix", ["page_id"])


def downgrade() -> None:
    op.drop_table("appliedfix")
    opportunity_type.drop(op.get_bind(), checkfirst=True)
    # Postgres can't drop a single enum value; leaving 'fix_verified' in
    # alerttype on downgrade is harmless (unused, not referenced by any row).
