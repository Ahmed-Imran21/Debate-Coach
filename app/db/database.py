from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


# pool_pre_ping guards against connections killed by a managed
# Postgres provider's idle timeout. pool_recycle keeps them
# below the usual 5 minute proxy cutoff.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=280,
    pool_size=10,
    max_overflow=10,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
