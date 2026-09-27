"""let an alert be about an account rather than a page, and record its email

The owner can now message a customer from the admin panel - when granting
credits, or on its own. That message is an Alert like any other so it appears in
the same bell, but it is not about a page, so `page_id` becomes nullable and a
new `message` type joins the enum.

`ALTER TYPE ... ADD VALUE` is safe here in a way migration 0007 was not: the new
Python member is named `message` and valued `"message"`, identical strings.
SQLAlchemy stores an Enum column by member *name*, and it was a name that
differed from its value (`pass_` vs `pass`) that silently broke every audit in
production last time.

The email columns live here rather than in their own table because the alert is
the durable record: if SMTP fails the message must still reach the user in-app,
and `email_status` is how the admin panel says what actually happened.

**SQLite needs the whole thing in batch mode.** It has no ALTER COLUMN, and it
cannot add a column carrying a foreign key either, so Alembic copies the table -
and it refuses to copy a constraint it cannot name, which alert's foreign keys
are. ALERT_BEFORE hands it the definition so nothing has to be reflected. This is
not a Postgres-only path: the dev database is SQLite.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

# Batch mode reflects the table to copy it, and refuses to copy a constraint it
# cannot name - alert's two foreign keys were created unnamed by migration 0004.
# Handing Alembic the definition sidesteps reflection entirely, which is the
# documented answer and far less fragile than hoping a naming convention catches
# everything. This mirrors the table as 0004/0005 left it.
ALERT_BEFORE = sa.Table(
    "alert",
    sa.MetaData(),
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
    sa.Column("page_id", sa.Integer(), sa.ForeignKey("page.id"), nullable=False),
    # 0004 sized this VARCHAR(10), which "fix_verified" already exceeds by two.
    # SQLite never enforced it; the rebuild quietly drops the limit.
    sa.Column("alert_type", sa.String(), nullable=False),
    sa.Column("message", sa.String(), nullable=False),
    sa.Column("read", sa.Boolean(), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
)

NEW_COLUMNS = (
    ("subject", lambda: sa.Column("subject", sa.String(), nullable=True)),
    # The foreign key is named explicitly: batch mode adds it as a constraint in
    # its own right, and refuses an unnamed one. Postgres would have invented a
    # name, so this only ever surfaces on SQLite.
    ("actor_id", lambda: sa.Column(
        "actor_id", sa.Integer(), sa.ForeignKey("user.id", name="fk_alert_actor_id_user"), nullable=True,
    )),
    ("email_status", lambda: sa.Column("email_status", sa.String(), nullable=True)),
    ("email_error", lambda: sa.Column("email_error", sa.String(), nullable=True)),
)


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # IF NOT EXISTS so a re-run - Render runs `alembic upgrade head` on every
        # cold start - cannot fail on an already-added label.
        op.execute("ALTER TYPE alerttype ADD VALUE IF NOT EXISTS 'message'")
        for _, column in NEW_COLUMNS:
            op.add_column("alert", column())
        op.alter_column("alert", "page_id", existing_type=sa.Integer(), nullable=True)
        return

    with op.batch_alter_table("alert", copy_from=ALERT_BEFORE) as batch:
        for _, column in NEW_COLUMNS:
            batch.add_column(column())
        batch.alter_column("page_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Any account-level alert has to go first, since page_id becomes required
    # again. The enum label stays: Postgres cannot drop one, and it is harmless.
    op.execute("DELETE FROM alert WHERE page_id IS NULL")

    if op.get_bind().dialect.name == "postgresql":
        for name, _ in reversed(NEW_COLUMNS):
            op.drop_column("alert", name)
        op.alter_column("alert", "page_id", existing_type=sa.Integer(), nullable=False)
        return

    after = ALERT_BEFORE.to_metadata(sa.MetaData())
    after.append_column(sa.Column("subject", sa.String(), nullable=True))
    after.append_column(sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True))
    after.append_column(sa.Column("email_status", sa.String(), nullable=True))
    after.append_column(sa.Column("email_error", sa.String(), nullable=True))
    with op.batch_alter_table("alert", copy_from=after) as batch:
        for name, _ in reversed(NEW_COLUMNS):
            batch.drop_column(name)
        batch.alter_column("page_id", existing_type=sa.Integer(), nullable=False)
