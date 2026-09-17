from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.draft_answer import DraftAnswer
from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.llm_gateway import openai_client
from app.services.tailoring.grounding import verify_grounding

GENERATION_SYSTEM_PROMPT = (
    "Write a concise, first-person answer to this job application question, for the "
    "candidate below applying to the specific job described. Ground every claim "
    "strictly in the candidate's real resume and project content — never invent "
    "experience, skills, metrics, or achievements not present in that content. "
    "Some questions ask about things a resume cannot answer — visa or work "
    "authorization status, salary expectations, notice period, willingness to "
    "relocate. If the candidate's material does not address what the question asks, "
    "write a short honest placeholder saying so instead of inventing a plausible "
    "answer — this draft is reviewed by the candidate before anything is submitted."
)


async def generate_draft_answer(profile: Profile, job: JobModel, question_text: str) -> str:
    completion = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"CANDIDATE RESUME AND PROJECTS:\n{profile.full_resume_text}\n\n"
                    f"JOB: {job.title} at {job.company}\n\n"
                    f"JOB DESCRIPTION:\n{job.description or '(no description available)'}\n\n"
                    f"APPLICATION QUESTION:\n{question_text}"
                ),
            },
        ],
    )
    content = completion.choices[0].message.content
    if content is None:
        raise ValueError("LLM returned no content for draft answer generation.")
    return content


async def ensure_draft_answer(
    application: Application,
    profile: Profile,
    job: JobModel,
    question_text: str,
    db: AsyncSession,
) -> DraftAnswer:
    """Cache-once per (application, question) pair — never regenerate on a hit,
    the same idempotency discipline as ensure_cover_letter.
    """
    result = await db.execute(
        select(DraftAnswer).where(
            DraftAnswer.application_id == application.id,
            DraftAnswer.question_text == question_text,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    content = await generate_draft_answer(profile, job, question_text)
    # A draft answer, unlike a cover letter, is often pasted into a form field
    # near-verbatim rather than read and rewritten first — that raises the cost of
    # an unflagged hallucination, so this artifact gets the verification pass.
    verification = await verify_grounding(content, profile.full_resume_text)

    draft_answer = DraftAnswer(
        application_id=application.id,
        question_text=question_text,
        answer_text=content,
        unverified_claims=verification.unverified_claims,
    )
    db.add(draft_answer)
    await db.commit()
    return draft_answer
