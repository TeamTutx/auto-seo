"""add alert table

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

alert_type = sa.Enum("score_drop", "new_fail", name="alerttype")


def upgrade() -> None:
    op.create_table(
        "alert",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("page.id"), nullable=False),
        sa.Column("alert_type", alert_type, nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_alert_user_id", "alert", ["user_id"])
    op.create_index("ix_alert_page_id", "alert", ["page_id"])


def downgrade() -> None:
    op.drop_table("alert")
    alert_type.drop(op.get_bind(), checkfirst=True)
