from app.models.job import Job as JobModel
from app.models.profile import Profile
from tests.integration.conftest import vector as _vector


async def test_ranking_puts_hard_filter_failure_last_despite_best_semantic_match(db, client) -> None:
    profile = Profile(
        name="Test Candidate",
        resume_text="...",
        years_experience=2.0,
        embedding=_vector(1.0, 0.0),
    )
    # cos_sim(profile, job) = 0.8 — a good but not perfect semantic match, meets requirement
    job_good_match = JobModel(
        external_id="good-match",
        source="greenhouse",
        title="Good Match",
        company="acme",
        location=None,
        url="https://example.test/1",
        embedding=_vector(0.8, 0.6),
        requirements={"min_years_experience": 1.0, "remote_allowed": None},
    )
    # cos_sim = 0.3 — a weaker semantic match, still meets requirement
    job_weak_match = JobModel(
        external_id="weak-match",
        source="greenhouse",
        title="Weak Match",
        company="acme",
        location=None,
        url="https://example.test/2",
        embedding=_vector(0.3, 0.9539392),
        requirements={"min_years_experience": 1.0, "remote_allowed": None},
    )
    # cos_sim = 1.0 — a PERFECT semantic match, but requires 10 years (profile has 2)
    job_fails_requirement = JobModel(
        external_id="fails-requirement",
        source="greenhouse",
        title="Perfect Match On Paper",
        company="acme",
        location=None,
        url="https://example.test/3",
        embedding=_vector(1.0, 0.0),
        requirements={"min_years_experience": 10.0, "remote_allowed": None},
    )
    db.add_all([profile, job_good_match, job_weak_match, job_fails_requirement])
    await db.commit()
    await db.refresh(profile)

    response = await client.get(f"/api/v1/profiles/{profile.id}/matches")

    assert response.status_code == 200
    matches = response.json()
    assert [m["job"]["title"] for m in matches] == [
        "Good Match",
        "Weak Match",
        "Perfect Match On Paper",
    ]
    # the hard filter zeroes the score outright — best raw similarity still loses
    assert matches[2]["score"] == 0.0
    assert matches[0]["score"] > matches[1]["score"] > 0.0


async def test_matches_404s_for_unknown_profile(client) -> None:
    response = await client.get("/api/v1/profiles/999999/matches")
    assert response.status_code == 404


async def test_matches_422s_when_profile_has_no_embedding(db, client) -> None:
    profile = Profile(name="No Embedding Yet", resume_text="...", years_experience=1.0)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    response = await client.get(f"/api/v1/profiles/{profile.id}/matches")

    assert response.status_code == 422
