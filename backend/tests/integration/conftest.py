import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.v1.deps import get_db
from app.main import app
from app.models.base import Base
from app.models.cover_letter import CoverLetter
from app.models.job import EMBEDDING_DIM
from app.models.job import Job as JobModel
from app.models.profile import Profile, ProfileProject
from app.models.resume_variant import ResumeVariant

TEST_DATABASE_URL = "postgresql+asyncpg://autoapply:autoapply@localhost:5432/autoapply_test"

test_engine = create_async_engine(TEST_DATABASE_URL)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


def vector(*leading: float) -> list[float]:
    """A controllable EMBEDDING_DIM-length vector for pgvector tests — only the
    leading values matter for the cosine similarity math, the rest is zero padding.
    """
    return list(leading) + [0.0] * (EMBEDDING_DIM - len(leading))


@pytest.fixture(scope="session")
async def create_test_schema():
    # Base.metadata.create_all bypasses Alembic, so migrations that enable extensions
    # (c612a86ae86a_enable_pgvector_extension) never run against this test DB — the
    # `vector` type used by Job.embedding/Profile.embedding must be enabled here instead.
    async with test_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture
async def db(create_test_schema):
    async with TestSession() as session:
        # CoverLetter and ResumeVariant both have FKs into profiles/jobs — must go
        # first, or deleting either of those violates the foreign key constraint
        # (found by actually running this once CoverLetter existed, not anticipated
        # in advance — applying the same lesson proactively for ResumeVariant now).
        await session.execute(delete(CoverLetter))
        await session.execute(delete(ResumeVariant))
        await session.execute(delete(ProfileProject))
        await session.execute(delete(Profile))
        await session.execute(delete(JobModel))
        await session.commit()
        yield session


@pytest.fixture
async def client(db):
    """An httpx client that exercises the real app/routes, sharing this test's own
    db session — so rows a test sets up are visible to the route without a second
    commit, and nothing here ever opens a connection on a different event loop.
    """

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()