"""
Database configuration and connection
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData
from sqlalchemy.pool import AsyncAdaptedQueuePool

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

# Create session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

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

async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)