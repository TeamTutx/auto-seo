"""add googleconnection table, gsc/ga property columns on site

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site", sa.Column("gsc_property", sa.String(), nullable=True))
    op.add_column("site", sa.Column("ga_property_id", sa.String(), nullable=True))

    op.create_table(
        "googleconnection",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, unique=True),
        sa.Column("access_token_encrypted", sa.String(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.String(), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False, server_default=""),
        sa.Column("connected_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_googleconnection_user_id", "googleconnection", ["user_id"])


def downgrade() -> None:
    op.drop_table("googleconnection")
    op.drop_column("site", "ga_property_id")
    op.drop_column("site", "gsc_property")
