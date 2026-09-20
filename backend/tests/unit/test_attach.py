from unittest.mock import AsyncMock, patch

import pytest

from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.models.resume_variant import ResumeVariant
from app.services.tailoring.attach import (
    MIN_ROLE_SIMILARITY,
    cosine_similarity,
    select_resume_variant,
)


def make_profile() -> Profile:
    return Profile(
        id=1, name="Ada", email="ada@example.dev", resume_text="...", years_experience=1.0
    )


def make_job(title: str) -> JobModel:
    return JobModel(
        id=1,
        external_id="x",
        source="greenhouse",
        title=title,
        company="acme",
        location=None,
        url="https://example.test/1",
        description="...",
    )


def fake_db(variants: list[ResumeVariant]):
    """Stands in for the one query select_resume_variant makes."""
    result = AsyncMock()
    result.scalars = lambda: type("S", (), {"all": lambda self: variants})()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


def vectors(mapping: dict[str, list[float]]):
    """embed_text stubbed to return a fixed vector per exact input string."""

    async def _embed(text: str) -> list[float]:
        return mapping[text]

    return _embed


def test_cosine_similarity_matches_hand_computed_values() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)
    assert cosine_similarity([3.0, 4.0], [3.0, 4.0]) == pytest.approx(1.0)


def test_cosine_similarity_of_a_zero_vector_is_zero_not_a_crash() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


async def test_no_variants_means_no_selection() -> None:
    variant = await select_resume_variant(make_profile(), make_job("ML Engineer"), fake_db([]))

    assert variant is None


async def test_picks_the_closest_variant_to_the_job_title() -> None:
    backend = ResumeVariant(id=1, profile_id=1, role_label="Backend Engineer", generated_content="x")
    ml = ResumeVariant(id=2, profile_id=1, role_label="Machine Learning Engineer", generated_content="y")

    with patch(
        "app.services.tailoring.attach.embed_text",
        new=vectors(
            {
                "ML Engineer (Full Stack)": [1.0, 0.0],
                "Backend Engineer": [0.0, 1.0],  # orthogonal - far below threshold
                "Machine Learning Engineer": [1.0, 0.0],  # identical - similarity 1.0
            }
        ),
    ):
        chosen = await select_resume_variant(
            make_profile(), make_job("ML Engineer (Full Stack)"), fake_db([backend, ml])
        )

    assert chosen is ml


async def test_an_unrelated_variant_is_refused_in_favour_of_the_base_resume() -> None:
    """Measured live: "Machine Learning Engineer" scores 0.534 against a
    Frontend Engineer posting — close enough to look plausible, wrong enough
    that sending that resume is worse than sending the untailored one.
    """
    frontend = ResumeVariant(
        id=1, profile_id=1, role_label="Frontend Engineer", generated_content="x"
    )

    # exactly the real measured pair, just below the calibrated threshold
    with patch(
        "app.services.tailoring.attach.embed_text",
        new=vectors({"Machine Learning Engineer": [1.0, 0.0], "Frontend Engineer": [0.534, 0.8455]}),
    ):
        chosen = await select_resume_variant(
            make_profile(), make_job("Machine Learning Engineer"), fake_db([frontend])
        )

    assert chosen is None


async def test_a_single_variant_still_has_to_clear_the_threshold() -> None:
    """The one-variant case must not shortcut past the check — that is exactly
    when a candidate is most likely to have a variant for a different role.
    """
    only = ResumeVariant(id=1, profile_id=1, role_label="Backend Engineer", generated_content="x")

    with patch(
        "app.services.tailoring.attach.embed_text",
        new=vectors({"Registered Nurse": [1.0, 0.0], "Backend Engineer": [0.0, 1.0]}),
    ):
        chosen = await select_resume_variant(
            make_profile(), make_job("Registered Nurse"), fake_db([only])
        )

    assert chosen is None


def test_threshold_sits_between_the_measured_match_and_non_match_scores() -> None:
    """Guards the calibration in attach.py's comment: 0.591 was the lowest
    should-match pair and 0.534 the highest should-not, so the threshold has to
    stay inside that gap. A first guess of 0.45 did not.
    """
    assert 0.534 < MIN_ROLE_SIMILARITY < 0.591
