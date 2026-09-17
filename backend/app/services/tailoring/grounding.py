from pydantic import BaseModel

from app.services.llm_gateway import openai_client

# Shared by every tailoring artifact that puts LLM-generated text in front of an
# employer: resume variants and draft answers both submit content verbatim, so
# both need the same anti-hallucination check against the candidate's real words.
VERIFICATION_SYSTEM_PROMPT = (
    "Compare the generated content against the candidate's original source "
    "material. List any specific skill, tool, technology, metric, or claim that "
    "appears in the generated content but is NOT supported — even in different "
    "wording — by the source material. Be conservative: only flag claims that are "
    "genuinely unsupported. Return an empty list if everything is well-grounded."
)


class VerificationResult(BaseModel):
    unverified_claims: list[str]


async def verify_grounding(generated_content: str, source_content: str) -> VerificationResult:
    completion = await openai_client.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": VERIFICATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"SOURCE MATERIAL:\n{source_content}\n\nGENERATED CONTENT:\n{generated_content}",
            },
        ],
        response_format=VerificationResult,
    )
    message = completion.choices[0].message
    if message.parsed is None:
        raise ValueError(f"LLM did not return valid structured output: {message.refusal}")
    return message.parsed
