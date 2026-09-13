"""add location_code, language_code, device to keywordrank

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-13

Rank results vary by search location/language/device; recording what a
measurement was checked against is what makes later rows comparable.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("keywordrank", sa.Column("location_code", sa.Integer(), nullable=False, server_default="2840"))
    op.add_column("keywordrank", sa.Column("language_code", sa.String(), nullable=False, server_default="en"))
    op.add_column("keywordrank", sa.Column("device", sa.String(), nullable=False, server_default="desktop"))


def downgrade() -> None:
    op.drop_column("keywordrank", "device")
    op.drop_column("keywordrank", "language_code")
    op.drop_column("keywordrank", "location_code")
