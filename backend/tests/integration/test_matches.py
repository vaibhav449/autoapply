from app.models.job import Job as JobModel
from app.models.profile import Profile, TargetLevel
from tests.integration.conftest import vector as _vector


async def test_ranking_puts_hard_filter_failure_last_despite_best_semantic_match(db, client) -> None:
    profile = Profile(
        name="Test Candidate",
        email="test@example.dev",
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
        requirements={
            "min_years_experience": 10.0,
            "remote_allowed": None,
            "experience_evidence": "Must have 10+ years of backend experience.",
        },
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
    # Tier beats similarity: the perfect semantic match still ranks last. But it is
    # demoted rather than zeroed — at 2 years against a 10-year ask it's a stretch,
    # not a disqualification, and the score survives so the UI can still show it.
    assert [m["tier"] for m in matches] == ["qualified", "qualified", "stretch"]
    assert matches[2]["experience"] == "fail"
    assert matches[2]["score"] > matches[0]["score"]
    assert "Asks 10+ years — you have 2" in matches[2]["note"]
    assert "Must have 10+ years of backend experience." in matches[2]["note"]
    assert matches[0]["note"] is None


async def test_unverified_jobs_rank_below_a_stretch_they_outscore(db, client) -> None:
    """The inversion that started all this: a job whose requirements we could not
    read must not outrank one we checked and found merely ambitious.
    """
    profile = Profile(
        name="Test Candidate",
        email="tiers@example.dev",
        resume_text="...",
        years_experience=1.0,
        embedding=_vector(1.0, 0.0),
    )
    # cos_sim = 1.0, but nothing is known about its requirements
    job_unknown = JobModel(
        external_id="unknown-reqs",
        source="adzuna",
        title="Truncated Description",
        company="acme",
        location=None,
        url="https://example.test/4",
        embedding=_vector(1.0, 0.0),
        requirements={"min_years_experience": None, "remote_allowed": None},
    )
    # cos_sim = 0.8 — a weaker match, but we know it asks 3 years
    job_stretch = JobModel(
        external_id="stretch-reqs",
        source="greenhouse",
        title="Known Stretch",
        company="acme",
        location=None,
        url="https://example.test/5",
        embedding=_vector(0.8, 0.6),
        requirements={"min_years_experience": 3.0, "remote_allowed": None},
    )
    db.add_all([profile, job_unknown, job_stretch])
    await db.commit()
    await db.refresh(profile)

    response = await client.get(f"/api/v1/profiles/{profile.id}/matches")

    matches = response.json()
    assert [m["job"]["title"] for m in matches] == ["Known Stretch", "Truncated Description"]
    assert [m["tier"] for m in matches] == ["stretch", "unverified"]
    # the unverified job wins on raw similarity and still loses on tier
    assert matches[1]["score"] > matches[0]["score"]
    assert matches[1]["experience"] == "unknown"
    assert "not stated" in matches[1]["note"]


async def test_matches_404s_for_unknown_profile(client) -> None:
    response = await client.get("/api/v1/profiles/999999/matches")
    assert response.status_code == 404


async def test_matches_422s_when_profile_has_no_embedding(db, client) -> None:
    profile = Profile(
        name="No Embedding Yet", email="noembed@example.dev", resume_text="...", years_experience=1.0
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    response = await client.get(f"/api/v1/profiles/{profile.id}/matches")

    assert response.status_code == 422


async def test_entry_level_jobs_get_reserved_candidate_slots(db, client) -> None:
    """Measured on the real pool: for a strong junior resume the nearest
    entry-level job sat at rank 128 by pure similarity, far outside a top-20
    candidate pool. Re-ranking cannot rescue a job that was never scored, so
    slots are held back for level-appropriate titles.
    """
    profile = Profile(
        name="Junior Candidate",
        email="junior@example.dev",
        resume_text="...",
        years_experience=1.0,
        target_level=TargetLevel.JUNIOR,
        embedding=_vector(1.0, 0.0),
    )
    # 25 near-perfect matches asking more experience than the candidate has
    crowd = [
        JobModel(
            external_id=f"crowd-{i}",
            source="greenhouse",
            title=f"Platform Engineer {i}",
            company="acme",
            location=None,
            url=f"https://example.test/crowd/{i}",
            embedding=_vector(1.0, 0.0),
            requirements={"min_years_experience": 9.0, "remote_allowed": None},
        )
        for i in range(25)
    ]
    # a genuinely reachable internship, but a much weaker semantic match
    internship = JobModel(
        external_id="the-internship",
        source="greenhouse",
        title="Software Engineer Intern",
        company="acme",
        location=None,
        url="https://example.test/intern",
        embedding=_vector(0.3, 0.9539392),
        requirements={"min_years_experience": 0.0, "remote_allowed": None},
    )
    db.add_all([profile, *crowd, internship])
    await db.commit()
    await db.refresh(profile)

    response = await client.get(f"/api/v1/profiles/{profile.id}/matches")

    matches = response.json()
    titles = [m["job"]["title"] for m in matches]
    assert "Software Engineer Intern" in titles, "entry-level job never reached scoring"
    # and being the only qualifying job, it outranks all 25 closer matches
    assert titles[0] == "Software Engineer Intern"
    assert matches[0]["tier"] == "qualified"


async def test_a_senior_seeker_keeps_the_whole_pool(db, client) -> None:
    profile = Profile(
        name="Senior Candidate",
        email="senior@example.dev",
        resume_text="...",
        years_experience=9.0,
        target_level=TargetLevel.SENIOR,
        embedding=_vector(1.0, 0.0),
    )
    senior_role = JobModel(
        external_id="senior-role",
        source="greenhouse",
        title="Senior Platform Engineer",
        company="acme",
        location=None,
        url="https://example.test/senior",
        embedding=_vector(1.0, 0.0),
        requirements={"min_years_experience": 8.0, "remote_allowed": None},
    )
    db.add_all([profile, senior_role])
    await db.commit()
    await db.refresh(profile)

    matches = (await client.get(f"/api/v1/profiles/{profile.id}/matches")).json()

    # the senior-title filter must apply only to candidates seeking entry level
    assert [m["job"]["title"] for m in matches] == ["Senior Platform Engineer"]
    assert matches[0]["tier"] == "qualified"
