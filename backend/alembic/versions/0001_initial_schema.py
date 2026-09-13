"""initial schema: users, sites, pages, audits, checks, keyword_ranks

Revision ID: 0001
Revises:
Create Date: 2026-09-13

Hand-written (no live Postgres available to autogenerate against) to mirror
app/models.py exactly. Regenerate with `alembic revision --autogenerate`
against a real DB if the two ever drift.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

plan_tier = sa.Enum("free", "pro", "agency", name="plantier")
verification_method = sa.Enum("dns_txt", "meta_tag", "file_upload", name="verificationmethod")
check_status = sa.Enum("pass", "warning", "fail", name="checkstatus")


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("plan", plan_tier, nullable=False, server_default="free"),
        sa.Column("credits_balance", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_user_email", "user", ["email"], unique=True)

    op.create_table(
        "site",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verification_method", verification_method, nullable=True),
        sa.Column("verification_token", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_site_user_id", "site", ["user_id"])

    op.create_table(
        "page",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("site.id"), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("target_keyword", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_page_site_id", "page", ["site_id"])

    op.create_table(
        "audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("page.id"), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("extracted_title", sa.String(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_page_id", "audit", ["page_id"])

    op.create_table(
        "check",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audit.id"), nullable=False),
        sa.Column("check_type", sa.String(), nullable=False),
        sa.Column("status", check_status, nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("suggested_fix", sa.String(), nullable=True),
    )
    op.create_index("ix_check_audit_id", "check", ["audit_id"])

    op.create_table(
        "keywordrank",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("page_id", sa.Integer(), sa.ForeignKey("page.id"), nullable=False),
        sa.Column("keyword", sa.String(), nullable=False),
        sa.Column("rank_position", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_keywordrank_page_id", "keywordrank", ["page_id"])


def downgrade() -> None:
    op.drop_table("keywordrank")
    op.drop_table("check")
    op.drop_table("audit")
    op.drop_table("page")
    op.drop_table("site")
    op.drop_table("user")
    check_status.drop(op.get_bind(), checkfirst=True)
    verification_method.drop(op.get_bind(), checkfirst=True)
    plan_tier.drop(op.get_bind(), checkfirst=True)
