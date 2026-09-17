from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.api.v1.routers.profiles import (
    create_profile,
    get_profile,
    list_profiles,
    update_profile,
)
from app.models.profile import Profile, TargetLevel
from app.schemas.profile import ProfileCreate, ProfileUpdate
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
    email="ada@example.dev",
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


async def test_update_profile_changes_only_the_fields_sent(db, mock_embeddings) -> None:
    created = await create_profile(PROFILE_PAYLOAD, db)
    mock_embeddings.reset_mock()

    updated = await update_profile(created.id, ProfileUpdate(location="Remote"), db)

    assert updated.location == "Remote"
    assert updated.name == "Ada Lovelace"  # untouched
    assert updated.years_experience == 5.5  # untouched
    mock_embeddings.assert_not_awaited()  # resume text never touched, no re-embed


async def test_update_profile_target_level(db, mock_embeddings) -> None:
    created = await create_profile(PROFILE_PAYLOAD, db)

    updated = await update_profile(created.id, ProfileUpdate(target_level=TargetLevel.INTERN), db)

    assert updated.target_level == TargetLevel.INTERN

    result = await db.execute(select(Profile).where(Profile.id == created.id))
    assert result.scalar_one().target_level == TargetLevel.INTERN


async def test_update_profile_resume_text_triggers_re_embedding(db, mock_embeddings) -> None:
    created = await create_profile(PROFILE_PAYLOAD, db)
    mock_embeddings.reset_mock()

    await update_profile(created.id, ProfileUpdate(resume_text="Now a frontend engineer."), db)

    mock_embeddings.assert_awaited_once()


async def test_update_profile_identical_resume_text_does_not_re_embed(db, mock_embeddings) -> None:
    created = await create_profile(PROFILE_PAYLOAD, db)
    mock_embeddings.reset_mock()

    await update_profile(created.id, ProfileUpdate(resume_text=PROFILE_PAYLOAD.resume_text), db)

    mock_embeddings.assert_not_awaited()


async def test_update_profile_404_for_missing_id(db) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await update_profile(999999, ProfileUpdate(location="Remote"), db)

    assert exc_info.value.status_code == 404


async def test_update_profile_rejects_an_invalid_email(db, mock_embeddings) -> None:
    created = await create_profile(PROFILE_PAYLOAD, db)

    with pytest.raises(ValidationError):
        ProfileUpdate(email="not-an-email")

    # the profile is unaffected by the attempt
    result = await db.execute(select(Profile).where(Profile.id == created.id))
    assert result.scalar_one().email == "ada@example.dev"
