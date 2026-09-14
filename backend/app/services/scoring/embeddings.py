from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.llm_gateway import openai_client

# Matches EMBEDDING_DIM in app/models/job.py — text-embedding-3-small's native size.
EMBEDDING_MODEL = "text-embedding-3-small"


async def embed_text(text: str) -> list[float]:
    response = await openai_client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


async def embed_job(job: JobModel, db: AsyncSession) -> None:
    header = job.title if not job.location else f"{job.title} ({job.location})"
    text = header if not job.description else f"{header}\n\n{job.description}"
    job.embedding = await embed_text(text)
    await db.commit()


async def embed_profile(profile: Profile, db: AsyncSession) -> None:
    profile.embedding = await embed_text(profile.full_resume_text)
    await db.commit()


async def embed_unembedded_jobs(db: AsyncSession, batch_size: int = 200) -> int:
    """Backfill embeddings for jobs discovery hasn't embedded yet. Returns how many were done."""
    result = await db.execute(select(JobModel).where(JobModel.embedding.is_(None)).limit(batch_size))
    jobs = result.scalars().all()
    for job in jobs:
        await embed_job(job, db)
    return len(jobs)
