from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text, event
from bot.config import settings
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = (
    f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=3,
    max_overflow=5,
    pool_recycle=300,
    pool_pre_ping=True,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    },
)

@event.listens_for(engine.sync_engine, "connect")
def disable_prepared_statements(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("DEALLOCATE ALL")
    cursor.close()

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_session():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def check_connection():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connected successfully")
        return True
    except Exception:
        logger.exception("Database connection failed")
        return False