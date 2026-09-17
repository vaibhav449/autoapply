from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.models.resume_variant import ResumeVariant
from app.services.llm_gateway import openai_client
from app.services.scoring.embeddings import embed_text
from app.services.tailoring.grounding import VerificationResult, verify_grounding  # noqa: F401

# VerificationResult/verify_grounding are re-exported, not just used internally:
# existing tests and callers import them from this module, and patch
# verify_grounding here by name — moving the implementation to grounding.py must
# not move those.

GENERATION_SYSTEM_PROMPT = (
    "Rewrite the candidate's resume content below to emphasize what's most relevant "
    "for the given role. Ground every claim strictly in the candidate's own resume/"
    "project content — never invent experience, skills, or metrics not present there. "
    "The example job descriptions below are for context only, to understand what this "
    "type of role typically values — never attribute a skill, tool, or claim to the "
    "candidate unless it already appears in their own resume or project text."
)


async def find_representative_jds(role_label: str, db: AsyncSession, limit: int = 15) -> list[JobModel]:
    """Real market signal for a role, not a single job's requirements — a cluster
    of real postings pulled the same way rank_jobs_for_profile finds candidates,
    just queried by a role description instead of a profile's embedding.
    """
    role_vector = await embed_text(role_label)
    result = await db.execute(
        select(JobModel)
        .where(JobModel.embedding.is_not(None), JobModel.description.is_not(None))
        .order_by(JobModel.embedding.cosine_distance(role_vector))
        .limit(limit)
    )
    return list(result.scalars().all())


async def generate_resume_variant(
    profile: Profile, role_label: str, emphasis_note: str | None, sample_jobs: list[JobModel]
) -> str:
    market_signal = "\n\n".join(
        f"- {job.title} at {job.company}: {(job.description or '')[:500]}" for job in sample_jobs
    )
    emphasis_line = f"EMPHASIS NOTE FROM CANDIDATE: {emphasis_note}\n\n" if emphasis_note else ""

    completion = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"TARGET ROLE: {role_label}\n\n"
                    f"CANDIDATE RESUME AND PROJECTS:\n{profile.full_resume_text}\n\n"
                    f"{emphasis_line}"
                    f"EXAMPLE JOB DESCRIPTIONS FOR THIS ROLE (context only, not facts "
                    f"about the candidate):\n{market_signal}"
                ),
            },
        ],
    )
    content = completion.choices[0].message.content
    if content is None:
        raise ValueError("LLM returned no content for resume variant generation.")
    return content


async def create_resume_variant(
    profile: Profile, role_label: str, emphasis_note: str | None, db: AsyncSession
) -> ResumeVariant:
    sample_jobs = await find_representative_jds(role_label, db)
    content = await generate_resume_variant(profile, role_label, emphasis_note, sample_jobs)
    verification = await verify_grounding(content, profile.full_resume_text)

    variant = ResumeVariant(
        profile_id=profile.id,
        role_label=role_label,
        emphasis_note=emphasis_note,
        generated_content=content,
        unverified_claims=verification.unverified_claims,
    )
    db.add(variant)
    await db.commit()
    return variant
