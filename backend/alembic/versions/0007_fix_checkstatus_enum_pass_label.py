"""rename checkstatus enum value 'pass' to 'pass_' (Postgres)

SQLAlchemy persists a Python Enum by member *name*, and the member is
`CheckStatus.pass_` (`pass` is a reserved word), but 0001 created the Postgres
type with the label 'pass'. Every audit that included a passing check then
failed to insert its Check rows on Postgres - the audit row (score) was already
committed, leaving a page with a score and an empty checklist. SQLite doesn't
enforce enum labels, which is why this only showed up in production.

No existing rows can hold 'pass' (inserting one is exactly what failed), so a
plain rename is safe. Guarded so it's a no-op if already applied.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-18
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _rename_label(old: str, new: str) -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'checkstatus' AND e.enumlabel = '{old}'
            ) THEN
                ALTER TYPE checkstatus RENAME VALUE '{old}' TO '{new}';
            END IF;
        END $$;
    """)


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _rename_label("pass", "pass_")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _rename_label("pass_", "pass")
