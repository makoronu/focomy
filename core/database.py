"""Database configuration and session management."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


# Parse SSL mode from database URL or environment
def _get_ssl_context():
    """Get SSL context for database connection."""
    db_url = settings.database_url
    # Check for ssl=disable or sslmode=disable in URL
    if "ssl=disable" in db_url or "sslmode=disable" in db_url:
        return False
    # Check for Fly.io internal network
    if ".flycast:" in db_url or ".internal:" in db_url:
        return False
    # Default to require SSL for external connections
    return True


# Remove ssl parameter from URL if present (asyncpg handles it differently)
def _clean_database_url(url: str) -> str:
    """Remove SSL-related parameters from URL."""
    import re

    # Remove ?ssl=... or &ssl=...
    url = re.sub(r"[?&]ssl(mode)?=[^&]*", "", url)
    # Clean up double && or trailing &
    url = re.sub(r"&&+", "&", url)
    url = re.sub(r"\?&", "?", url)
    url = url.rstrip("?&")
    return url


_connect_args = {}
_ssl_mode = _get_ssl_context()
if not _ssl_mode:
    _connect_args["ssl"] = False

engine = create_async_engine(
    _clean_database_url(settings.database_url),
    echo=False,
    future=True,
    connect_args=_connect_args,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


async def get_db() -> AsyncSession:
    """Dependency for getting database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    # Import models to register them with Base
    from . import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connection."""
    await engine.dispose()
