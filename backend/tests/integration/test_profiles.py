from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.routers.profiles import create_profile, get_profile, list_profiles
from app.models.profile import Profile
from app.schemas.profile import ProfileCreate
from app.services.llm_gateway import openai_client

FAKE_EMBEDDING = [0.1] * 1536


@pytest.fixture
def mock_embeddings(monkeypatch):
    fake_response = SimpleNamespace(data=[SimpleNamespace(embedding=FAKE_EMBEDDING)])
    mock_create = AsyncMock(return_value=fake_response)
    monkeypatch.setattr(openai_client.embeddings, "create", mock_create)
    return mock_create


PROFILE_PAYLOAD = ProfileCreate(
    name="Ada Lovelace",
    resume_text="Experienced backend engineer with a focus on distributed systems.",
    years_experience=5.5,
    preferences={"remote_only": True},
    projects=[
        {"title": "Analytical Engine", "content_md": "Built a general-purpose computer."},
        {"title": "Notes on the Engine", "content_md": "Wrote the first algorithm."},
    ],
)


async def test_create_profile_persists_fields_projects_and_embedding(db, mock_embeddings) -> None:
    profile = await create_profile(PROFILE_PAYLOAD, db)

    assert profile.name == "Ada Lovelace"
    assert profile.years_experience == 5.5
    assert profile.preferences == {"remote_only": True}
    assert len(profile.projects) == 2
    assert {p.title for p in profile.projects} == {"Analytical Engine", "Notes on the Engine"}
    assert profile.embedding is not None
    assert len(profile.embedding) == 1536
    mock_embeddings.assert_awaited_once()

    result = await db.execute(select(Profile).where(Profile.id == profile.id))
    reloaded = result.scalar_one()
    assert reloaded.embedding == FAKE_EMBEDDING


async def test_get_profile_returns_created_profile_with_projects(db, mock_embeddings) -> None:
    created = await create_profile(PROFILE_PAYLOAD, db)

    fetched = await get_profile(created.id, db)

    assert fetched.id == created.id
    assert len(fetched.projects) == 2


async def test_get_profile_404_for_missing_id(db) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_profile(999999, db)

    assert exc_info.value.status_code == 404


async def test_list_profiles_includes_created_profile(db, mock_embeddings) -> None:
    await create_profile(PROFILE_PAYLOAD, db)

    profiles = await list_profiles(db)

    assert any(p.name == "Ada Lovelace" for p in profiles)
