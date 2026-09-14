from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cover_letter import CoverLetter
from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.llm_gateway import openai_client

SYSTEM_PROMPT = (
    "Write a short, tailored cover-letter-style pitch (2-3 short paragraphs) for the "
    "candidate below, for the specific job described. Ground every claim strictly in "
    "the candidate's real resume and project content given — never invent experience, "
    "skills, metrics, or achievements not present in that content."
)


async def generate_cover_letter(profile: Profile, job: JobModel) -> str:
    completion = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"CANDIDATE RESUME AND PROJECTS:\n{profile.full_resume_text}\n\n"
                    f"JOB: {job.title} at {job.company}\n\n"
                    f"JOB DESCRIPTION:\n{job.description or '(no description available)'}"
                ),
            },
        ],
    )
    content = completion.choices[0].message.content
    if content is None:
        raise ValueError("LLM returned no content for cover letter generation.")
    return content


async def ensure_cover_letter(profile: Profile, job: JobModel, db: AsyncSession) -> CoverLetter:
    """Cache-once per (profile, job) pair — never regenerate on a hit."""
    result = await db.execute(
        select(CoverLetter).where(
            CoverLetter.profile_id == profile.id, CoverLetter.job_id == job.id
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    content = await generate_cover_letter(profile, job)
    cover_letter = CoverLetter(profile_id=profile.id, job_id=job.id, content=content)
    db.add(cover_letter)
    await db.commit()
    return cover_letter
