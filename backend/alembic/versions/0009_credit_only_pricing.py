"""credit-only pricing: retire the subscription tiers, seed a pack ladder

Signal stopped selling Pro/Agency subscriptions: there is one tier, the same
limits for everyone (ACCOUNT_LIMITS in models.py), and the only thing for sale
is a pack of credits. The owner creates as many packs as they like in
/admin/pricing, so what this seeds is a starting point, not a fixed catalog.

- product.badge: the "Best value" flag on a pricing card.
- payment.product_key: which pack a payment bought, so the admin panel can show
  revenue per price point and a renamed or retired pack keeps its history.
- The pro/agency rows are deleted. Nothing referenced them by foreign key - a
  `payment` records what it bought in its own `plan`/`product_key` text columns -
  and money already taken is untouched.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-19
"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

# Keep in step with DEFAULT_PRODUCTS in app/services/billing.py, which seeds the
# same ladder into databases built by create_all() (local dev has no migrations).
PACKS = [
    {"key": "credits_10", "name": "10 credits", "price_cents": 200, "credits": 10,
     "description": "Enough to try a few rank checks", "badge": None, "sort_order": 10},
    {"key": "credits_50", "name": "50 credits", "price_cents": 500, "credits": 50,
     "description": "For a site you're actively working on", "badge": "Best value", "sort_order": 20},
    {"key": "credits_200", "name": "200 credits", "price_cents": 1500, "credits": 200,
     "description": "For agencies and multiple sites", "badge": None, "sort_order": 30},
]

product = sa.table(
    "product",
    sa.column("id", sa.Integer),
    sa.column("key", sa.String),
    sa.column("name", sa.String),
    sa.column("kind", sa.String),
    sa.column("price_cents", sa.Integer),
    sa.column("interval", sa.String),
    sa.column("plan", sa.String),
    sa.column("credits", sa.Integer),
    sa.column("dodo_product_id", sa.String),
    sa.column("description", sa.String),
    sa.column("badge", sa.String),
    sa.column("active", sa.Boolean),
    sa.column("sort_order", sa.Integer),
    sa.column("updated_at", sa.DateTime),
)


def upgrade() -> None:
    op.add_column("product", sa.Column("badge", sa.String(), nullable=True))
    op.add_column("payment", sa.Column("product_key", sa.String(), nullable=True))

    connection = op.get_bind()
    now = datetime.utcnow()

    op.execute(sa.delete(product).where(product.c.kind == "subscription"))

    existing = {row[0]: row[1] for row in connection.execute(sa.select(product.c.key, product.c.price_cents))}
    for pack in PACKS:
        values = dict(pack, kind="credit_pack", interval=None, plan=None, active=True, updated_at=now)
        if pack["key"] not in existing:
            op.execute(sa.insert(product).values(dodo_product_id=None, **values))
        elif pack["key"] == "credits_50" and existing["credits_50"] == 900:
            # 0008 seeded this at $9 and nobody has repriced it, so move it onto
            # the new ladder. A price the owner has actually edited is left alone.
            op.execute(
                sa.update(product)
                .where(product.c.key == "credits_50")
                .values(price_cents=500, description=pack["description"], badge=pack["badge"], updated_at=now)
            )


def downgrade() -> None:
    now = datetime.utcnow()
    op.execute(sa.delete(product).where(product.c.key.in_(["credits_10", "credits_200"])))
    op.execute(
        sa.insert(product).values(
            [
                {"key": "pro", "name": "Pro", "kind": "subscription", "price_cents": 2400, "interval": "month",
                 "plan": "pro", "credits": 0, "dodo_product_id": None, "description": None, "badge": None,
                 "active": True, "sort_order": 10, "updated_at": now},
                {"key": "agency", "name": "Agency", "kind": "subscription", "price_cents": 8900, "interval": "month",
                 "plan": "agency", "credits": 0, "dodo_product_id": None, "description": None, "badge": None,
                 "active": True, "sort_order": 20, "updated_at": now},
            ]
        )
    )
    with op.batch_alter_table("payment") as batch:
        batch.drop_column("product_key")
    with op.batch_alter_table("product") as batch:
        batch.drop_column("badge")
