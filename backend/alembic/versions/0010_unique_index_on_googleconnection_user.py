"""make ix_googleconnection_user_id unique, matching the model

Migration 0006 declared `user_id` both `unique=True` (which Postgres implemented
as a separate UNIQUE *constraint*) and `index=True` (a plain, non-unique index).
The model says `Field(index=True, unique=True)`, which SQLModel renders as a
single UNIQUE *index*. Uniqueness was enforced either way, so nothing was ever
broken - but the shapes differed, which meant `alembic check` always reported
drift and so couldn't be used to prove a rebuilt database matches the models
(see docs/DATABASE.md).

Postgres only. A SQLite database built by create_all() already has the unique
index, and SQLite can't drop an unnamed constraint without rewriting the table.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-19
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

CONSTRAINT = "googleconnection_user_id_key"
INDEX = "ix_googleconnection_user_id"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # One transaction, so user_id is never briefly un-unique for a concurrent writer.
    op.execute(f'ALTER TABLE googleconnection DROP CONSTRAINT IF EXISTS "{CONSTRAINT}"')
    op.drop_index(INDEX, table_name="googleconnection", if_exists=True)
    op.create_index(INDEX, "googleconnection", ["user_id"], unique=True)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_index(INDEX, table_name="googleconnection", if_exists=True)
    op.create_index(INDEX, "googleconnection", ["user_id"])
    op.create_unique_constraint(CONSTRAINT, "googleconnection", ["user_id"])
