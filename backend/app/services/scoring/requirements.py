from pydantic import BaseModel

from app.models.profile import Profile
from app.services.llm_gateway import openai_client


class JobRequirements(BaseModel):
    min_years_experience: float | None = None
    remote_allowed: bool | None = None


async def extract_job_requirements(description_text: str) -> JobRequirements:
    completion = await openai_client.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract the minimum years of experience required, and whether "
                    "remote work is explicitly allowed, from this job description. "
                    "Use null for anything not clearly stated — do not guess."
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


def meets_experience_requirement(profile: Profile, requirements: JobRequirements) -> bool:
    """Deterministic, exact comparison — no embeddings, no fuzziness."""
    if requirements.min_years_experience is None:
        return True
    return profile.years_experience >= requirements.min_years_experience
