from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.scoring.requirements import JobRequirements, meets_experience_requirement


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
