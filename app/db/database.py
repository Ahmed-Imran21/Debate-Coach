from collections.abc import Generator

from google.cloud.sql.connector import Connector
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


def _build_engine():

    if settings.cloud_sql_connection_name:

        # Routes through the Cloud SQL Python Connector, which
        # handles the mTLS/IAM handshake to the instance's Unix
        # socket without a proxy sidecar. The DSN is left blank;
        # every real connection comes from getconn() instead.
        #
        # Driver is pg8000, not psycopg: the connector only
        # supports pg8000/asyncpg/pymysql/pytds as of v1.21 (no
        # psycopg driver exists for it). The dialect prefix below
        # has to match, since SQLAlchemy uses it to interpret the
        # raw connection getconn() returns. Local/direct
        # connections below still use psycopg via database_url.
        connector = Connector()

        def getconn():
            return connector.connect(
                settings.cloud_sql_connection_name,
                "pg8000",
                user=settings.db_user,
                password=settings.db_password,
                db=settings.db_name,
            )

        return create_engine(
            "postgresql+pg8000://",
            creator=getconn,
            pool_pre_ping=True,
            pool_recycle=280,
            pool_size=10,
            max_overflow=10,
        )

    # Local development, or any Postgres reachable directly by
    # URL.
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=280,
        pool_size=10,
        max_overflow=10,
    )


# pool_pre_ping guards against connections killed by a managed
# Postgres provider's idle timeout. pool_recycle keeps them
# below the usual 5 minute proxy cutoff.
engine = _build_engine()

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
