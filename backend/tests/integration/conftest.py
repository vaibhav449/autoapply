import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.job import Job as JobModel

TEST_DATABASE_URL = "postgresql+asyncpg://autoapply:autoapply@localhost:5432/autoapply_test"

test_engine = create_async_engine(TEST_DATABASE_URL)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
async def create_test_schema():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture
async def db(create_test_schema):
    async with TestSession() as session:
        await session.execute(delete(JobModel))
        await session.commit()
        yield session