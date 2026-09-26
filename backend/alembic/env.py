from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from app import models  # noqa: F401  (registers tables on SQLModel.metadata)
from app.database import DATABASE_URL

config = context.config
# DATABASE_URL, not settings.database_url: app/database.py rewrites a legacy
# `postgres://` prefix, which SQLAlchemy 2 refuses with "Can't load plugin:
# sqlalchemy.dialects:postgres". Alembic builds its own engine, so taking the
# raw setting here meant the app tolerated that URL and every deploy still died
# on `alembic upgrade head` - which is exactly how the Aiven cutover failed,
# because Aiven's console hands out the `postgres://` form.
#
# The %-escaping is for ConfigParser, which would otherwise read a `%` in a
# generated password as interpolation syntax.
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
