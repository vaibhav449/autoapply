import enum
import hashlib
import re
from itertools import pairwise

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.llm_gateway import openai_client

# Bump whenever the prompt or JobRequirements shape changes. It feeds the cache
# fingerprint, so raising it re-extracts every row — the description is only half
# of what an extraction depends on.
EXTRACTION_VERSION = "5"


class Verdict(str, enum.Enum):
    """UNKNOWN exists because "the description never said" and "the candidate
    qualifies" are different facts. Collapsing them into a bool is what let jobs
    with unreadable requirements outrank jobs we had actually checked.
    """

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class JobRequirements(BaseModel):
    min_years_experience: float | None = Field(
        default=None,
        description=(
            "Minimum years of professional experience explicitly required. "
            "For a range like '2-12 years', use the lower bound. "
            "Null if the description does not clearly state one."
        ),
    )
    remote_allowed: bool | None = Field(
        default=None,
        description="True only if remote work is explicitly allowed. Null if unstated.",
    )
    experience_evidence: str | None = Field(
        default=None,
        description=(
            "The sentence stating the experience requirement, copied verbatim from "
            "the description. Null if min_years_experience is null."
        ),
    )
    must_have_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Named technologies the description explicitly REQUIRES. Each entry must "
            "be a proper noun you would find in a technology index — for example "
            "Python, Go, Kubernetes, PostgreSQL, React, AWS, Kafka. "
            "NEVER include: job functions ('backend engineering', 'solutions "
            "architecture'), generic activities ('coding', 'automations', 'tools', "
            "'workflows'), soft skills ('communication skills'), or domains and "
            "concepts ('distributed systems', 'machine learning', 'scalable "
            "systems', 'REST APIs'). "
            "NEVER include anything listed as preferred, bonus, or nice-to-have. "
            "At most 5. Return an empty list if the description names no specific "
            "required technologies — an empty list is the correct and common answer."
        ),
    )


async def extract_job_requirements(description_text: str) -> JobRequirements:
    completion = await openai_client.chat.completions.parse(
        model="gpt-4o-mini",
        # Deterministic on purpose: the result is cached permanently, so sampling
        # variance would freeze one unlucky extraction onto the row forever.
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract hiring requirements from this job description. "
                    "Job descriptions state experience requirements in many forms — "
                    "'7+ years', 'minimum 3 years', '2-12 years', 'at least five years'. "
                    "Read the whole description, including any 'Minimum requirements' or "
                    "'Ideal candidate' section, before answering. "
                    "For must_have_skills, list only hard technical requirements the "
                    "description states as required — never items under 'preferred', "
                    "'bonus' or 'nice to have'. "
                    "Use null or an empty list for anything not clearly stated — do not "
                    "guess or infer from the job title."
                ),
            },
            {"role": "user", "content": description_text},
        ],
        response_format=JobRequirements,
    )

    message = completion.choices[0].message
    if message.parsed is None:
        raise ValueError(f"LLM did not return valid structured output: {message.refusal}")
    return message.parsed


def description_fingerprint(description: str | None) -> str:
    """Identifies the text AND the extraction logic a cached result came from."""
    payload = f"{EXTRACTION_VERSION}:{description or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


async def ensure_job_requirements(job: JobModel, db: AsyncSession) -> JobRequirements:
    """Extract once per (job, description) pair, and re-extract whenever the
    description changes.

    Caching on row identity alone silently poisons the pool: a job extracted
    before its description was backfilled caches an all-null placeholder, and a
    plain cache hit then serves that forever even once the real text arrives.
    """
    if job.description is None:
        # Nothing to extract from, so persist nothing. Caching an empty placeholder
        # here is precisely what poisoned rows whose description arrived later, and
        # writing one would also destroy requirements extracted earlier.
        return (
            JobRequirements.model_validate(job.requirements)
            if job.requirements is not None
            else JobRequirements()
        )

    fingerprint = description_fingerprint(job.description)
    if job.requirements is not None and job.requirements_fingerprint == fingerprint:
        return JobRequirements.model_validate(job.requirements)

    requirements = await extract_job_requirements(job.description)
    job.requirements = requirements.model_dump()
    job.requirements_fingerprint = fingerprint
    await db.commit()
    return requirements


async def extract_missing_requirements(db: AsyncSession, batch_size: int = 100) -> int:
    """Pre-extract requirements for jobs nothing has scored yet. Returns how many.

    Extraction used to happen only for the ~20 candidates a ranking request looked
    at, which left 98% of the pool unevaluated — including 142 entry-level jobs a
    junior candidate could actually take. A job nobody has read can never be
    matched, so the whole pool gets annotated in the background instead.
    """
    result = await db.execute(
        select(JobModel)
        .where(
            JobModel.requirements.is_(None),
            JobModel.description.is_not(None),
            JobModel.closed_at.is_(None),
        )
        .limit(batch_size)
    )
    jobs = list(result.scalars().all())
    for job in jobs:
        await ensure_job_requirements(job, db)
    return len(jobs)


def experience_verdict(profile: Profile, requirements: JobRequirements) -> Verdict:
    """Deterministic, exact comparison — no embeddings, no fuzziness."""
    if requirements.min_years_experience is None:
        return Verdict.UNKNOWN
    if profile.years_experience >= requirements.min_years_experience:
        return Verdict.PASS
    return Verdict.FAIL


# Aggregators cut the description short and mark the cut with an ellipsis. Measured
# against the live pool this matches 249 of 259 Adzuna rows and zero of the 975
# Greenhouse/Lever rows, so it identifies an excerpt without misreading full text.
EXCERPT_MAX_LENGTH = 500


def description_is_truncated(description: str | None) -> bool:
    """Whether we hold only an excerpt, rather than the posting's real text.

    This matters more than it looks: requirements extracted from an excerpt are
    not "the job has no requirements", they are "we never saw them". The job that
    exposed this states "Must have 7+ years" in a section the excerpt cuts off.
    """
    if description is None:
        return False
    stripped = description.rstrip()
    return len(description) <= EXCERPT_MAX_LENGTH and stripped.endswith("…")


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _canonical_skill(skill: str) -> str:
    return _NON_ALNUM.sub("", skill.lower())


def profile_skill_keys(text: str) -> set[str]:
    """Every word, plus adjacent 2- and 3-word concatenations.

    Matching against concatenated runs rather than raw substrings is what lets
    "Node.js", "Node JS" and "NodeJS" collapse onto one key while stopping "Go"
    from matching "Google" — the same substring trap that scored "Internal Audit"
    as an internship during the seniority analysis.

    Public (not the original leading-underscore name) because a caller scoring
    many jobs against one profile tokenizes this once and reuses it — see
    rank_jobs_for_profile, which previously called missing_skills per candidate
    and re-tokenized the full resume text from scratch every time.
    """
    words = [word for word in _NON_ALNUM.split(text.lower()) if word]
    keys = set(words)
    keys.update(a + b for a, b in pairwise(words))
    keys.update(a + b + c for a, b, c in zip(words, words[1:], words[2:], strict=False))
    return keys


def missing_required_skills(available_keys: set[str], required: list[str]) -> list[str]:
    """Required skills absent from an already-tokenized key set — the reusable
    half of missing_skills, for a caller that already has profile_skill_keys().
    """
    return [skill for skill in required if _canonical_skill(skill) not in available_keys]


def missing_skills(profile_text: str, required: list[str]) -> list[str]:
    """Required skills the profile never mentions. Deterministic — no LLM, no
    embeddings, so a rejection can always be explained by naming the exact skill.

    One-shot convenience wrapper: tokenizes profile_text on every call, so a
    caller scoring many jobs against the same profile should call
    profile_skill_keys() once instead and use missing_required_skills() directly.
    """
    return missing_required_skills(profile_skill_keys(profile_text), required)


def experience_note(
    profile: Profile, requirements: JobRequirements, verdict: Verdict
) -> str | None:
    """Human-readable reason, quoting the source sentence where we have one, so a
    wrong extraction is visible and arguable rather than an unexplained ranking.
    """
    if verdict is Verdict.UNKNOWN:
        return "Experience requirement not stated in the available description"
    if verdict is Verdict.FAIL:
        asked = f"{requirements.min_years_experience:g}"
        held = f"{profile.years_experience:g}"
        note = f"Asks {asked}+ years — you have {held}"
        if requirements.experience_evidence:
            return f'{note}. "{requirements.experience_evidence}"'
        return note
    return None
