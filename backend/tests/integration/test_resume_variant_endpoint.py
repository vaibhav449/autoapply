from unittest.mock import AsyncMock, patch

from app.models.profile import Profile
from app.services.tailoring.resume_variant import VerificationResult
from tests.integration.conftest import vector


async def test_create_then_list_resume_variant(db, client) -> None:
    profile = Profile(
        name="Test Candidate", email="test@example.dev", resume_text="...", years_experience=2.0
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    with (
        patch(
            "app.services.tailoring.resume_variant.embed_text",
            new=AsyncMock(return_value=vector(1.0, 0.0)),
        ),
        patch(
            "app.services.tailoring.resume_variant.generate_resume_variant",
            new=AsyncMock(return_value="Tailored resume content."),
        ),
        patch(
            "app.services.tailoring.resume_variant.verify_grounding",
            new=AsyncMock(return_value=VerificationResult(unverified_claims=["Kubernetes"])),
        ),
    ):
        create_response = await client.post(
            f"/api/v1/profiles/{profile.id}/resume-variants",
            json={"role_label": "Backend Engineer", "emphasis_note": "emphasize APIs"},
        )

    assert create_response.status_code == 200
    body = create_response.json()
    assert body["role_label"] == "Backend Engineer"
    assert body["generated_content"] == "Tailored resume content."
    assert body["unverified_claims"] == ["Kubernetes"]

    list_response = await client.get(f"/api/v1/profiles/{profile.id}/resume-variants")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["role_label"] == "Backend Engineer"


async def test_duplicate_role_label_is_409(db, client) -> None:
    profile = Profile(
        name="Test Candidate", email="test@example.dev", resume_text="...", years_experience=2.0
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    with (
        patch(
            "app.services.tailoring.resume_variant.embed_text",
            new=AsyncMock(return_value=vector(1.0, 0.0)),
        ),
        patch(
            "app.services.tailoring.resume_variant.generate_resume_variant",
            new=AsyncMock(return_value="Content."),
        ),
        patch(
            "app.services.tailoring.resume_variant.verify_grounding",
            new=AsyncMock(return_value=VerificationResult(unverified_claims=[])),
        ),
    ):
        first = await client.post(
            f"/api/v1/profiles/{profile.id}/resume-variants",
            json={"role_label": "Backend Engineer"},
        )
        second = await client.post(
            f"/api/v1/profiles/{profile.id}/resume-variants",
            json={"role_label": "Backend Engineer"},
        )

    assert first.status_code == 200
    assert second.status_code == 409


async def test_404s_for_unknown_profile(client) -> None:
    response = await client.get("/api/v1/profiles/999999/resume-variants")
    assert response.status_code == 404
