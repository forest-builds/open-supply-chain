"""
Test infrastructure.

DB tests require a running Postgres instance. Set DATABASE_URL to a test DB:

    docker compose up -d postgres
    DATABASE_URL=postgresql+asyncpg://state:state@localhost:5432/the_state_test \
        uv run pytest tests/ -v
"""

import os
import sys
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

TEST_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://state:state@localhost:5432/the_state_test",
)

# Ensure all models are registered with Base.metadata before any fixture runs.
import models  # noqa: E402, F401
from core.db import Base, get_db  # noqa: E402
from main import app  # noqa: E402


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Per-test: fresh schema creation, session, then full teardown."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
