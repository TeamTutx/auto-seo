"""billing + admin tables: product, credittransaction, payment, adminauditlog

Also adds user.dodo_customer_id / user.dodo_subscription_id, seeds the default
products (Pro, Agency, a 50-credit pack - the draft prices from
docs/REQUIREMENTS.md, editable from /admin/pricing), and writes an
opening-balance ledger row per existing user so the credit ledger sums to every
balance from day one.

kind/reason/provider are plain strings, not Postgres enums (see models.py).

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-19
"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user", sa.Column("dodo_customer_id", sa.String(), nullable=True))
    op.add_column("user", sa.Column("dodo_subscription_id", sa.String(), nullable=True))
    op.create_index("ix_user_dodo_customer_id", "user", ["dodo_customer_id"])
    op.create_index("ix_user_dodo_subscription_id", "user", ["dodo_subscription_id"])

    product = op.create_table(
        "product",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("interval", sa.String(), nullable=True),
        sa.Column("plan", sa.String(), nullable=True),
        sa.Column("credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dodo_product_id", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_product_key", "product", ["key"], unique=True)

    op.create_table(
        "credittransaction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("ref", sa.String(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_credittransaction_user_id", "credittransaction", ["user_id"])

    op.create_table(
        "payment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("tax_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("plan", sa.String(), nullable=True),
        sa.Column("credits_granted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_ref", sa.String(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("provider", "provider_ref", name="uq_payment_provider_ref"),
    )
    op.create_index("ix_payment_user_id", "payment", ["user_id"])

    op.create_table(
        "adminauditlog",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_adminauditlog_target_user_id", "adminauditlog", ["target_user_id"])

    now = datetime.utcnow()
    op.bulk_insert(
        product,
        [
            {
                "key": "pro", "name": "Pro", "kind": "subscription", "price_cents": 2400,
                "interval": "month", "plan": "pro", "credits": 0, "dodo_product_id": None,
                "description": None, "active": True, "sort_order": 10, "updated_at": now,
            },
            {
                "key": "agency", "name": "Agency", "kind": "subscription", "price_cents": 8900,
                "interval": "month", "plan": "agency", "credits": 0, "dodo_product_id": None,
                "description": None, "active": True, "sort_order": 20, "updated_at": now,
            },
            {
                "key": "credits_50", "name": "50 credits", "kind": "credit_pack", "price_cents": 900,
                "interval": None, "plan": None, "credits": 50, "dodo_product_id": None,
                "description": "For extra rank checks and AI fixes", "active": True, "sort_order": 30,
                "updated_at": now,
            },
        ],
    )

    op.execute(
        """
        INSERT INTO credittransaction (user_id, delta, balance_after, reason, note, created_at)
        SELECT id, credits_balance, credits_balance, 'opening_balance',
               'Balance when the credit ledger started', CURRENT_TIMESTAMP
        FROM "user" WHERE credits_balance <> 0
        """
    )


def downgrade() -> None:
    op.drop_table("adminauditlog")
    op.drop_table("payment")
    op.drop_table("credittransaction")
    op.drop_table("product")
    with op.batch_alter_table("user") as batch:
        batch.drop_index("ix_user_dodo_subscription_id")
        batch.drop_index("ix_user_dodo_customer_id")
        batch.drop_column("dodo_subscription_id")
        batch.drop_column("dodo_customer_id")
