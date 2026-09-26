from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


def _url() -> str:
    """The configured URL, with the legacy `postgres://` scheme fixed.

    SQLAlchemy 2 only accepts `postgresql://`. Several providers still hand out
    the old form, and pasting one into DATABASE_URL would take the API down with
    an error that names neither the setting nor the provider."""
    url = settings.database_url
    return "postgresql://" + url[len("postgres://"):] if url.startswith("postgres://") else url


DATABASE_URL = _url()
_is_sqlite = DATABASE_URL.startswith("sqlite")

# Postgres now lives on a managed host in another region (Aiven, Bangalore; the
# API runs in Singapore), which changes two things about pooling:
#
# - **pool_pre_ping.** A connection idle across a network that drops it comes
#   back dead, and the failure lands on a user's request rather than at startup.
#   Pre-ping spends one round trip to find out first.
# - **A small pool.** The plan allows 20 connections and Aiven's own agents hold
#   about 13, so roughly 7 are left for everything Signal runs - the web process,
#   the in-process background jobs, and the `alembic upgrade head` that runs on
#   every deploy. SQLAlchemy's default (5 + 10 overflow) would exhaust that under
#   any concurrency; 2 + 3 stays inside it with room for a deploy overlapping.
_pool = {} if _is_sqlite else {
    "pool_size": 2,
    "max_overflow": 3,
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    **_pool,
)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
