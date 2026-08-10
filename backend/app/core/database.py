from pathlib import Path
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings

Base = declarative_base()

POSTGRES_DATABASE_URL = settings.DATABASE_URL
SQLITE_FALLBACK_PATH = Path(__file__).resolve().parents[2] / "privacyshield.db"
SQLITE_FALLBACK_URL = f"sqlite+aiosqlite:///{SQLITE_FALLBACK_PATH.as_posix()}"

# PostgreSQL is always the primary connection. SQLite is only selected after a
# connection or schema initialization failure.
engine = create_async_engine(POSTGRES_DATABASE_URL, echo=False, future=True)
database_backend = "PostgreSQL"

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    global engine, AsyncSessionLocal, database_backend

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.run_sync(Base.metadata.create_all)
        database_backend = "PostgreSQL"
    except Exception:
        await engine.dispose()
        engine = create_async_engine(SQLITE_FALLBACK_URL, echo=False, future=True)
        AsyncSessionLocal = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        database_backend = "SQLite fallback"
