from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.scoring.requirements import (
    JobRequirements,
    ensure_job_requirements,
    meets_experience_requirement,
)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return dot / (norm_a * norm_b)


def combine_score(semantic_similarity: float, meets_requirements: bool) -> float:
    """Combine the semantic layer and the structured hard-filter into one score.

    A failed hard requirement zeroes the score outright — a close semantic
    match doesn't rescue a candidate who doesn't meet a stated minimum.
    """
    if not meets_requirements:
        return 0.0
    return semantic_similarity


def score_profile_against_job(
    profile: Profile, job: JobModel, requirements: JobRequirements
) -> float:
    if profile.embedding is None or job.embedding is None:
        raise ValueError("Both profile and job need an embedding before scoring.")

    similarity = cosine_similarity(profile.embedding, job.embedding)
    meets = meets_experience_requirement(profile, requirements)
    return combine_score(similarity, meets)


async def rank_jobs_for_profile(
    profile: Profile, db: AsyncSession, candidate_pool: int = 20, limit: int = 10
) -> list[tuple[JobModel, float]]:
    """Two stages, deliberately: a fast SQL-only vector search narrows the whole pool
    down to a small candidate set first; only THOSE candidates ever trigger an LLM
    call (via ensure_job_requirements' cache). Never embed-or-extract per request
    against the full pool — that's hundreds of sequential API calls per ranking.
    """
    if profile.embedding is None:
        raise ValueError("Profile has no embedding yet.")

    result = await db.execute(
        select(JobModel)
        .where(JobModel.embedding.is_not(None))
        .order_by(JobModel.embedding.cosine_distance(profile.embedding))
        .limit(candidate_pool)
    )
    candidates = result.scalars().all()

    scored = []
    for job in candidates:
        requirements = await ensure_job_requirements(job, db)
        scored.append((job, score_profile_against_job(profile, job, requirements)))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]
