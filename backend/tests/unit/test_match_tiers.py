from datetime import UTC, datetime, timedelta

import pytest

from app.models.job import Job as JobModel
from app.models.profile import Profile, TargetLevel
from app.services.scoring.requirements import (
    JobRequirements,
    Verdict,
    description_is_truncated,
    experience_note,
    experience_verdict,
    missing_skills,
    profile_skill_keys,
)
from app.services.scoring.score import (
    MatchTier,
    classify_job_for_profile,
    title_is_above_target,
)


def make_profile(years: float, resume_text: str = "...") -> Profile:
    return Profile(
        name="Candidate",
        email="c@example.dev",
        resume_text=resume_text,
        years_experience=years,
        embedding=[1.0, 0.0],
    )


def make_job(embedding: list[float] | None = None, **overrides) -> JobModel:
    fields = {
        "external_id": "x",
        "source": "greenhouse",
        "title": "Engineer",
        "company": "acme",
        "location": None,
        "url": "https://example.test/1",
        "embedding": embedding or [1.0, 0.0],
    }
    return JobModel(**{**fields, **overrides})


@pytest.mark.parametrize(
    ("years_held", "years_asked", "expected"),
    [
        (5.0, 3.0, Verdict.PASS),
        (3.0, 3.0, Verdict.PASS),
        (1.0, 3.0, Verdict.FAIL),
        (1.0, None, Verdict.UNKNOWN),
        (0.0, 0.0, Verdict.PASS),
    ],
)
def test_experience_verdict(years_held, years_asked, expected) -> None:
    requirements = JobRequirements(min_years_experience=years_asked)

    assert experience_verdict(make_profile(years_held), requirements) is expected


def test_unknown_is_not_a_pass() -> None:
    """The whole point of the three-valued verdict: a missing requirement used to
    return True and let unreadable jobs outrank checked ones.
    """
    verdict = experience_verdict(make_profile(1.0), JobRequirements())

    assert verdict is Verdict.UNKNOWN
    assert verdict is not Verdict.PASS


@pytest.mark.parametrize(
    ("verdict", "tier"),
    [
        (Verdict.PASS, MatchTier.QUALIFIED),
        (Verdict.FAIL, MatchTier.STRETCH),
        (Verdict.UNKNOWN, MatchTier.UNVERIFIED),
    ],
)
def test_tier_ordering_puts_unverified_last(verdict, tier) -> None:
    assert MatchTier.QUALIFIED < MatchTier.STRETCH < MatchTier.UNVERIFIED
    years = {Verdict.PASS: 1.0, Verdict.FAIL: 9.0, Verdict.UNKNOWN: None}[verdict]

    result = classify_job_for_profile(
        make_profile(2.0), make_job(), JobRequirements(min_years_experience=years)
    )

    assert result.tier is tier


def test_note_quotes_the_source_sentence_when_available() -> None:
    requirements = JobRequirements(
        min_years_experience=7.0,
        experience_evidence="Must have 7+ years of hands-on Backend Engineering experience",
    )

    note = experience_note(make_profile(1.0), requirements, Verdict.FAIL)

    assert "Asks 7+ years — you have 1" in note
    assert "hands-on Backend Engineering" in note


def test_note_survives_a_missing_evidence_sentence() -> None:
    note = experience_note(make_profile(1.0), JobRequirements(min_years_experience=7.0), Verdict.FAIL)

    assert note == "Asks 7+ years — you have 1"


def test_fractional_years_are_not_rounded_in_the_note() -> None:
    requirements = JobRequirements(min_years_experience=2.5)

    note = experience_note(make_profile(1.5), requirements, Verdict.FAIL)

    assert note == "Asks 2.5+ years — you have 1.5"


def test_a_qualifying_job_carries_no_note() -> None:
    result = classify_job_for_profile(
        make_profile(9.0), make_job(), JobRequirements(min_years_experience=3.0)
    )

    assert result.tier is MatchTier.QUALIFIED
    assert result.note is None


RESUME = (
    "Backend engineer. Built services in Node.js and Python with FastAPI. "
    "Frontend in React.js 19. Deployed on Google Cloud with machine learning pipelines."
)


@pytest.mark.parametrize(
    ("required", "expected_missing"),
    [
        (["Python"], []),
        (["FastAPI"], []),
        (["Node.js"], []),
        (["NodeJS"], []),          # punctuation and spacing collapse to one key
        (["node js"], []),
        (["React"], []),           # bare token present in "React.js 19"
        (["Machine Learning"], []),  # adjacent-word concatenation
        (["Kubernetes"], ["Kubernetes"]),
        (["Python", "Rust"], ["Rust"]),
        ([], []),
    ],
)
def test_skill_matching(required, expected_missing) -> None:
    assert missing_skills(RESUME, required) == expected_missing


def test_short_skill_does_not_match_a_longer_word() -> None:
    """'Go' must not be satisfied by 'Google' — the substring trap that scored
    'Internal Audit' as an internship earlier in this work.
    """
    assert missing_skills(RESUME, ["Go"]) == ["Go"]


def test_no_skill_overlap_at_all_excludes_regardless_of_experience() -> None:
    profile = make_profile(20.0, RESUME)
    requirements = JobRequirements(
        min_years_experience=1.0, must_have_skills=["Salesforce", "NetSuite"]
    )

    result = classify_job_for_profile(profile, make_job(), requirements)

    assert result.tier is MatchTier.EXCLUDED
    assert result.score == 0.0
    assert result.note == "Matches none of the required: Salesforce, NetSuite"


def test_partial_skill_overlap_warns_instead_of_excluding() -> None:
    """A JD's skill list is usually a menu ("Go, Ruby, Java or Python"), so missing
    some of it is not a disqualification — requiring all of them excluded 17 of 20
    real candidates.
    """
    profile = make_profile(20.0, RESUME)
    requirements = JobRequirements(
        min_years_experience=1.0, must_have_skills=["Python", "Kubernetes"]
    )

    result = classify_job_for_profile(profile, make_job(), requirements)

    assert result.tier is MatchTier.QUALIFIED
    assert result.score > 0.0
    assert result.note == "Missing: Kubernetes"


def test_skill_gap_and_experience_gap_are_both_reported() -> None:
    profile = make_profile(1.0, RESUME)
    requirements = JobRequirements(
        min_years_experience=7.0, must_have_skills=["Python", "Kubernetes"]
    )

    result = classify_job_for_profile(profile, make_job(), requirements)

    assert result.tier is MatchTier.STRETCH
    assert result.note == "Missing: Kubernetes · Asks 7+ years — you have 1"


def test_matching_all_skills_leaves_the_experience_tier_intact() -> None:
    profile = make_profile(1.0, RESUME)
    requirements = JobRequirements(
        min_years_experience=5.0, must_have_skills=["Python", "React"]
    )

    result = classify_job_for_profile(profile, make_job(), requirements)

    assert result.tier is MatchTier.STRETCH
    assert result.score > 0.0


def test_no_extracted_skills_never_excludes() -> None:
    result = classify_job_for_profile(
        make_profile(5.0, RESUME), make_job(), JobRequirements(min_years_experience=1.0)
    )

    assert result.tier is MatchTier.QUALIFIED


def test_scoring_requires_embeddings_on_both_sides() -> None:
    profile = make_profile(3.0)
    profile.embedding = None

    with pytest.raises(ValueError):
        classify_job_for_profile(profile, make_job(), JobRequirements())


EXCERPT = "Design and build the core Node.js services and REST APIs; integrate…"
FULL_TEXT = "Design and build the core Node.js services. Minimum requirements 7+ years."


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        (EXCERPT, True),
        (FULL_TEXT, False),
        (None, False),
        ("", False),
        ("x" * 600 + "…", False),  # long enough to be real text, not an excerpt
    ],
)
def test_truncation_detection(description, expected) -> None:
    assert description_is_truncated(description) is expected


def test_a_truncated_posting_is_unverified_not_qualified() -> None:
    """The job that exposed this states "Must have 7+ years" in text the aggregator
    cut off. Reporting "requirement not stated" would be a false claim.
    """
    result = classify_job_for_profile(
        make_profile(1.0, RESUME), make_job(description=EXCERPT), JobRequirements()
    )

    assert result.tier is MatchTier.UNVERIFIED
    assert result.experience is Verdict.UNKNOWN
    assert "truncated excerpt" in result.note
    assert "not stated" not in result.note


def test_skills_extracted_from_an_excerpt_never_exclude() -> None:
    """Zero overlap against skills read out of a 500-character teaser is not
    evidence of anything — the rest of the requirements were never seen.
    """
    requirements = JobRequirements(must_have_skills=["Salesforce", "NetSuite"])

    result = classify_job_for_profile(
        make_profile(1.0, RESUME), make_job(description=EXCERPT), requirements
    )

    assert result.tier is MatchTier.UNVERIFIED
    assert "Matches none of the required" not in result.note
    assert result.score > 0.0


def test_a_recently_seen_job_is_not_stale() -> None:
    now = datetime(2026, 9, 16, tzinfo=UTC)
    job = make_job(last_seen_at=now - timedelta(hours=6))

    result = classify_job_for_profile(
        make_profile(5.0, RESUME), job, JobRequirements(min_years_experience=1.0), now=now
    )

    assert result.stale is False
    assert result.note is None


def test_a_long_unseen_job_is_flagged_and_dated() -> None:
    now = datetime(2026, 9, 16, tzinfo=UTC)
    job = make_job(last_seen_at=now - timedelta(days=9))

    result = classify_job_for_profile(
        make_profile(5.0, RESUME), job, JobRequirements(min_years_experience=1.0), now=now
    )

    assert result.stale is True
    assert "Last seen 9 days ago" in result.note
    # still qualified — staleness demotes and warns, it never claims closure
    assert result.tier is MatchTier.QUALIFIED


def test_staleness_is_reported_alongside_a_truncated_excerpt() -> None:
    now = datetime(2026, 9, 16, tzinfo=UTC)
    job = make_job(description=EXCERPT, last_seen_at=now - timedelta(days=4))

    result = classify_job_for_profile(
        make_profile(1.0, RESUME), job, JobRequirements(), now=now
    )

    assert result.stale is True
    assert "Last seen 4 days ago" in result.note
    assert "truncated excerpt" in result.note


def junior_profile(resume: str = RESUME) -> Profile:
    profile = make_profile(1.0, resume)
    profile.target_level = TargetLevel.JUNIOR
    return profile


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Senior Backend Engineer", True),
        ("Sr. Backend Engineer", True),
        ("Staff Software Engineer", True),
        ("Engineering Manager", True),
        ("Chief Technology Officer", True),   # reached a 1-year candidate's list once
        ("Backend Engineer", False),
        ("Software Engineer Intern", False),
    ],
)
def test_title_above_target_for_a_junior_seeker(title, expected) -> None:
    assert title_is_above_target(junior_profile(), make_job(title=title)) is expected


def test_a_senior_seeker_is_never_flagged_for_a_senior_title() -> None:
    profile = make_profile(9.0, RESUME)
    profile.target_level = TargetLevel.SENIOR

    assert title_is_above_target(profile, make_job(title="Senior Backend Engineer")) is False


def test_level_mismatch_is_reported_and_demotes_within_its_tier() -> None:
    result = classify_job_for_profile(
        junior_profile(),
        make_job(title="Principal Backend Engineer"),
        JobRequirements(min_years_experience=1.0),
    )

    assert result.level_mismatch is True
    assert "Titled above the junior level" in result.note
    # demoted, not excluded — the tier still reflects the experience check
    assert result.tier is MatchTier.QUALIFIED
    assert result.score > 0.0


def test_precomputed_skill_keys_produce_the_same_result_as_computing_them_inline() -> None:
    """Proves the rank_jobs_for_profile optimization (tokenize once, reuse per
    candidate) doesn't change behavior versus the original per-call tokenization.
    """
    profile = make_profile(1.0, RESUME)
    job = make_job()
    requirements = JobRequirements(min_years_experience=5.0, must_have_skills=["Python", "Rust"])

    default = classify_job_for_profile(profile, job, requirements)
    with_cache = classify_job_for_profile(
        profile, job, requirements, skill_keys=profile_skill_keys(RESUME)
    )

    assert with_cache == default
