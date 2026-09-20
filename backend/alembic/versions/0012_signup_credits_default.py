"""raise the free signup allowance to 10 credits

The number itself lives in SIGNUP_CREDITS (app/models.py) and that is what every
insert actually uses - the app always supplies the column. This migration exists
so the *schema* doesn't keep claiming 3: a column default that disagrees with
the application is the kind of quiet lie that sends someone debugging in the
wrong direction, and it is what a raw INSERT or a future data migration would
get.

Existing accounts are deliberately left alone. They already got the allowance
that was on offer when they signed up, and topping them up is a business
decision for the owner to make in /admin/users, not something a migration should
do silently.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user") as batch:
        batch.alter_column("credits_balance", existing_type=sa.Integer(), server_default="10")


def downgrade() -> None:
    with op.batch_alter_table("user") as batch:
        batch.alter_column("credits_balance", existing_type=sa.Integer(), server_default="3")
