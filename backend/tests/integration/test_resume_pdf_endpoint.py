from unittest.mock import patch

from app.models.profile import Profile
from app.models.resume_variant import ResumeVariant


async def make_profile_with_variant(db, name: str = "Ada Lovelace") -> tuple[Profile, ResumeVariant]:
    profile = Profile(
        name=name,
        email="ada@example.dev",
        phone="555-0100",
        location="London, UK",
        resume_text="Backend engineer.",
        years_experience=5.0,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    variant = ResumeVariant(
        profile_id=profile.id,
        role_label="Backend Engineer",
        generated_content="## Experience\n\nBuilt the Analytical Engine.\n",
        unverified_claims=[],
    )
    db.add(variant)
    await db.commit()
    await db.refresh(variant)
    return profile, variant


async def test_returns_a_pdf_with_a_sanitized_filename(db, client) -> None:
    profile, variant = await make_profile_with_variant(db)

    response = await client.get(
        f"/api/v1/profiles/{profile.id}/resume-variants/{variant.id}/pdf"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    assert (
        response.headers["content-disposition"]
        == 'inline; filename="Ada_Lovelace_Backend_Engineer.pdf"'
    )


async def test_bytes_are_rendered_once_then_served_from_the_row(db, client) -> None:
    profile, variant = await make_profile_with_variant(db)
    url = f"/api/v1/profiles/{profile.id}/resume-variants/{variant.id}/pdf"

    first = await client.get(url)
    await db.refresh(variant)
    assert variant.pdf_bytes == first.content

    with patch("app.services.tailoring.resume_pdf.render_resume_pdf") as render:
        second = await client.get(url)

    render.assert_not_called()
    assert second.content == first.content


async def test_404s_for_a_variant_belonging_to_another_profile(db, client) -> None:
    _, variant = await make_profile_with_variant(db)
    other, _ = await make_profile_with_variant(db, name="Grace Hopper")

    response = await client.get(
        f"/api/v1/profiles/{other.id}/resume-variants/{variant.id}/pdf"
    )

    assert response.status_code == 404


async def test_404s_for_an_unknown_variant(db, client) -> None:
    profile, _ = await make_profile_with_variant(db)

    response = await client.get(f"/api/v1/profiles/{profile.id}/resume-variants/999999/pdf")

    assert response.status_code == 404
