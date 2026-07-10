"""
Database configuration and connection
"""
import os
from contextvars import ContextVar
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

# Database URL - will be configurable via environment variables
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://postgres:postgres@localhost:5432/genetic_health_db"
)

# Create async engine with connection pooling for concurrent users
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL debugging
    future=True,
    poolclass=AsyncAdaptedQueuePool,
    pool_size=20,          # Persistent connections
    max_overflow=40,       # Extra connections under load (total max: 60)
    pool_timeout=30,       # Wait up to 30s for a connection
    pool_recycle=1800,     # Recycle connections every 30min
    pool_pre_ping=True,    # Verify connections before use
)

# Default session factory (bound to the main event loop's engine)
_default_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# ContextVar that background threads can set to a per-thread factory backed by
# a NullPool engine bound to the thread's own event loop.  All code that calls
# async_session_factory() automatically uses the override when it is set.
_session_factory_ctx: ContextVar = ContextVar('_session_factory_ctx', default=None)


class _SessionFactoryProxy:
    """Transparent callable proxy for the session factory.

    Returns sessions from the ContextVar override when one is active (i.e.
    inside a background thread that set its own NullPool engine), otherwise
    falls back to the default connection-pooled factory.

    This means *no call sites need to change* — ``async_session_factory()``
    just works correctly regardless of which event loop is running.
    """
    def __call__(self):
        override = _session_factory_ctx.get()
        return (override if override is not None else _default_session_factory)()


async_session_factory = _SessionFactoryProxy()


def make_thread_engine_and_factory():
    """Create an isolated async engine + session factory for use inside a
    background OS thread that runs its own event loop.

    Uses NullPool so every acquired connection is fresh and bound to the
    thread's loop — avoids "Future attached to a different loop" errors.
    Call ``await engine.dispose()`` when the thread's work is done.
    """
    _engine = create_async_engine(DATABASE_URL, poolclass=NullPool, echo=False, future=True)
    _factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine, _factory

# Base class for models
class Base(DeclarativeBase):
    metadata = MetaData()

async def get_session():
    """Dependency to get database session"""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

from sqlalchemy import text as sa_text

async def init_db():
    """Initialize database tables.

    If alembic has already applied migrations (alembic_version has rows),
    skip create_all to avoid collisions with alembic-managed indexes.
    Falls back to create_all only for fresh databases with no migrations yet.
    """
    async with engine.begin() as conn:
        try:
            result = await conn.execute(sa_text("SELECT version_num FROM alembic_version LIMIT 1"))
            if result.fetchone():
                return  # Schema fully managed by alembic migrations
        except Exception:
            pass
        await conn.run_sync(lambda c: Base.metadata.create_all(c, checkfirst=True))