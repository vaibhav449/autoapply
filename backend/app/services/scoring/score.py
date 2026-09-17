import enum
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job as JobModel
from app.models.profile import Profile, TargetLevel
from app.services.scoring.requirements import (
    JobRequirements,
    Verdict,
    description_is_truncated,
    ensure_job_requirements,
    experience_note,
    experience_verdict,
    missing_required_skills,
    profile_skill_keys,
)

# Adzuna is polled once daily, so a listing absent from two consecutive polls is
# worth flagging. It is NOT proof of closure — aggregator postings cannot be
# verified at all (their pages block us) — so this demotes and warns, never
# excludes. Boards we can verify get their closures via closed_at instead.
STALE_AFTER = timedelta(days=2)

TRUNCATED_NOTE = (
    "Only a truncated excerpt of this posting is available, so its requirements "
    "could not be checked — open the posting to confirm"
)

# Word boundaries matter: a plain substring scores "Internal Audit" as an
# internship. Measured on the real pool, an intern-titled role requires more than
# a year only 12% of the time versus 97-98% for everything else — so the title is
# useless for guessing a number but sharp at spotting level mismatch.
_SENIOR_WORDS = (
    "senior|sr|lead|principal|staff|architect|director|head|vp|chief|cto|cio|"
    "president|manager"
)

SENIOR_TITLE = re.compile(rf"\b({_SENIOR_WORDS})\b", re.IGNORECASE)

# Postgres spells word boundaries \m and \M rather than \b.
SENIOR_TITLE_SQL = rf"\m({_SENIOR_WORDS})\M"
ENTRY_TITLE_SQL = r"\m(intern|internship|fresher|graduate|trainee|junior|associate)\M"

# Candidate slots held back so the right jobs are actually scored. Measured: for a
# strong junior resume the nearest entry-level job sat at rank 128 by pure
# similarity, far outside the pool — and no amount of re-ranking can rescue a job
# that was never a candidate.
RESERVED_LEVEL_SLOTS = 8
# Slots for jobs whose extracted bar the candidate already clears. These only work
# because requirements are now pre-extracted in the background; previously 98% of
# the pool had no requirements on record to filter on.
RESERVED_QUALIFYING_SLOTS = 8

JUNIOR_TARGETS = frozenset({TargetLevel.INTERN, TargetLevel.NEW_GRAD, TargetLevel.JUNIOR})


def title_is_above_target(profile: Profile, job: JobModel) -> bool:
    return profile.target_level in JUNIOR_TARGETS and bool(SENIOR_TITLE.search(job.title))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return dot / (norm_a * norm_b)


class MatchTier(int, enum.Enum):
    """Ordered buckets rather than weighted penalties: there are no tunable
    constants to argue over, ordering is deterministic, and each bucket is a
    label the UI can show honestly.

    UNVERIFIED sits below STRETCH deliberately. A job we could not read the
    requirements for must not outrank one we checked and found reachable —
    that inversion is exactly what put a 7-years role at the top of a
    1-year candidate's list.
    """

    QUALIFIED = 0
    STRETCH = 1
    UNVERIFIED = 2
    # The one hard gate. Years is a warning because a years bar eliminates ~98% of
    # the pool for a junior candidate; a missing required technology is a real
    # disqualification, and one we can always name.
    EXCLUDED = 3


TIER_BY_VERDICT = {
    Verdict.PASS: MatchTier.QUALIFIED,
    Verdict.FAIL: MatchTier.STRETCH,
    Verdict.UNKNOWN: MatchTier.UNVERIFIED,
}


@dataclass(frozen=True)
class RankedJob:
    job: JobModel
    similarity: float
    tier: MatchTier
    experience: Verdict
    note: str | None
    stale: bool = False
    level_mismatch: bool = False

    @property
    def score(self) -> float:
        return 0.0 if self.tier is MatchTier.EXCLUDED else self.similarity


def _staleness_note(job: JobModel, now: datetime) -> str | None:
    if job.last_seen_at is None or (now - job.last_seen_at) <= STALE_AFTER:
        return None
    return f"Last seen {(now - job.last_seen_at).days} days ago — may no longer be open"


def classify_job_for_profile(
    profile: Profile,
    job: JobModel,
    requirements: JobRequirements,
    now: datetime | None = None,
    skill_keys: set[str] | None = None,
) -> RankedJob:
    """`now` is injectable so staleness stays deterministic under test.

    `skill_keys` lets a caller scoring many jobs against the same profile
    (rank_jobs_for_profile) tokenize the resume once and reuse it here, instead
    of every candidate re-tokenizing the full resume text from scratch. Omit it
    for a one-off call — it's computed on demand below.
    """
    if profile.embedding is None or job.embedding is None:
        raise ValueError("Both profile and job need an embedding before scoring.")

    now = now or datetime.now(UTC)
    keys = skill_keys if skill_keys is not None else profile_skill_keys(profile.full_resume_text)
    similarity = cosine_similarity(profile.embedding, job.embedding)
    stale_note = _staleness_note(job, now)
    above_target = title_is_above_target(profile, job)

    leading = []
    if above_target:
        leading.append(f"Titled above the {profile.target_level.value.replace('_', ' ')} level you're targeting")
    if stale_note:
        leading.append(stale_note)

    # An excerpt cannot support any claim about requirements — not the skills
    # extracted from it, and not the absence of an experience bar. Reporting
    # "requirement not stated" here would be false: the posting states one, in
    # text the aggregator cut off.
    if description_is_truncated(job.description):
        return RankedJob(
            job=job,
            similarity=similarity,
            tier=MatchTier.UNVERIFIED,
            experience=Verdict.UNKNOWN,
            note=" · ".join([*leading, TRUNCATED_NOTE]),
            stale=stale_note is not None,
            level_mismatch=above_target,
        )

    verdict = experience_verdict(profile, requirements)
    required = requirements.must_have_skills
    absent = missing_required_skills(keys, required)

    # Exclude only on NO overlap at all. Requiring every listed skill excluded 17 of
    # 20 real candidates, because a JD's skill list is usually a menu ("Go, Ruby,
    # Java or Python") rather than a checklist. Zero overlap is the version that is
    # actually defensible, and it can always be explained by naming the whole list.
    if required and len(absent) == len(required):
        return RankedJob(
            job=job,
            similarity=similarity,
            tier=MatchTier.EXCLUDED,
            experience=verdict,
            note=" · ".join(
                [*leading, f"Matches none of the required: {', '.join(required)}"]
            ),
            stale=stale_note is not None,
            level_mismatch=above_target,
        )

    notes = list(leading)
    if absent:
        notes.append(f"Missing: {', '.join(absent)}")
    if years_note := experience_note(profile, requirements, verdict):
        notes.append(years_note)

    return RankedJob(
        job=job,
        similarity=similarity,
        tier=TIER_BY_VERDICT[verdict],
        experience=verdict,
        note=" · ".join(notes) or None,
        stale=stale_note is not None,
        level_mismatch=above_target,
    )


async def rank_jobs_for_profile(
    profile: Profile, db: AsyncSession, candidate_pool: int = 32, limit: int = 15
) -> list[RankedJob]:
    """Two stages, deliberately: a fast SQL-only vector search narrows the whole pool
    down to a small candidate set first; only THOSE candidates ever trigger an LLM
    call (via ensure_job_requirements' cache). Never embed-or-extract per request
    against the full pool — that's hundreds of sequential API calls per ranking.
    """
    if profile.embedding is None:
        raise ValueError("Profile has no embedding yet.")

    conditions = [JobModel.embedding.is_not(None), JobModel.closed_at.is_(None)]
    seeking_entry = profile.target_level in JUNIOR_TARGETS
    if seeking_entry:
        # A strong junior resume embeds close to senior work, so pure vector
        # distance fills the pool with roles the candidate cannot take.
        conditions.append(~JobModel.title.op("~*")(SENIOR_TITLE_SQL))

    async def nearest(limit: int, extra=()) -> list[JobModel]:
        result = await db.execute(
            select(JobModel)
            .where(*conditions, *extra)
            .order_by(JobModel.embedding.cosine_distance(profile.embedding))
            .limit(limit)
        )
        return list(result.scalars().all())

    reserved = RESERVED_QUALIFYING_SLOTS + (RESERVED_LEVEL_SLOTS if seeking_entry else 0)
    groups = [
        await nearest(candidate_pool - reserved),
        # Jobs whose stated bar this candidate already clears. Without a reserved
        # group these lose every slot to closer semantic matches asking 6+ years.
        await nearest(
            RESERVED_QUALIFYING_SLOTS,
            (
                JobModel.requirements["min_years_experience"].as_float()
                <= profile.years_experience,
            ),
        ),
    ]
    if seeking_entry:
        groups.append(
            await nearest(RESERVED_LEVEL_SLOTS, (JobModel.title.op("~*")(ENTRY_TITLE_SQL),))
        )

    by_id = {job.id: job for group in groups for job in group}
    candidates = list(by_id.values())

    # Tokenized once per request, not once per candidate: classify_job_for_profile
    # used to call missing_skills(profile.full_resume_text, ...) itself, re-running
    # this over the whole resume for every one of up to candidate_pool candidates.
    keys = profile_skill_keys(profile.full_resume_text)

    ranked = []
    for job in candidates:
        requirements = await ensure_job_requirements(job, db)
        ranked.append(classify_job_for_profile(profile, job, requirements, skill_keys=keys))

    # Stale sorts after fresh within a tier: a posting we haven't seen in days is
    # a worse bet than an equally-matched one we saw this morning.
    ranked.sort(key=lambda r: (r.tier, r.level_mismatch, r.stale, -r.similarity))
    return ranked[:limit]
