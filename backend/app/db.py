from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.settings import get_settings


class Base(DeclarativeBase):
    pass


_url = get_settings().sqlalchemy_url
_is_sqlite = _url.startswith("sqlite")
engine = create_engine(
    _url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {},
)

if _is_sqlite:
    # The collector thread writes while the API reads
    @event.listens_for(engine, "connect")
    def _sqlite_wal(conn, _):
        conn.execute("PRAGMA journal_mode=WAL")

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    from app import models  # noqa: F401  registers tables

    Base.metadata.create_all(engine)
    # create_all does not add columns to existing tables; small additive changes go here
    for table, col, ddl in (("versions", "sources", "JSON"), ("web_searches", "prompt_version", "INTEGER DEFAULT 0")):
        if col not in {c["name"] for c in inspect(engine).get_columns(table)}:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
