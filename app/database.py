"""Database engine and session management.

Works with both SQLite (local dev / tests) and PostgreSQL (Railway) from a
single DATABASE_URL. Railway sometimes hands out URLs with the legacy
``postgres://`` scheme, which SQLAlchemy 2 no longer accepts, so we rewrite it.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


settings = get_settings()

_url = _normalize_url(settings.database_url)
_connect_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}

engine = create_engine(_url, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI dependency that yields a request-scoped session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
