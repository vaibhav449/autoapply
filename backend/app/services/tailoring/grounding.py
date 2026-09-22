from pydantic import BaseModel

from app.models.profile import Profile
from app.services.llm_gateway import openai_client

# Bump whenever the verification prompt changes. A stored draft answer keeps the
# flags this check produced, so those go stale when the check does — even though
# the answer text itself is untouched. Feeding this into the answer fingerprint
# is what makes the old flags get recomputed rather than served indefinitely.
VERIFICATION_VERSION = "2"

# Shared by every tailoring artifact that puts LLM-generated text in front of an
# employer: resume variants and draft answers both submit content verbatim, so
# both need the same anti-hallucination check against the candidate's real words.
VERIFICATION_SYSTEM_PROMPT = (
    "Compare the generated content against the candidate's original source "
    "material. List any specific skill, tool, technology, metric, or claim that "
    "appears in the generated content but is NOT supported — even in different "
    "wording — by the source material. Be conservative: only flag claims that are "
    "genuinely unsupported. Return an empty list if everything is well-grounded.\n\n"
    "Flag only things the candidate is asserting about themselves: experience, "
    "skills, tools, employers, education, metrics, achievements. In particular, "
    "do NOT flag any of the following, none of which is a claim that could be "
    "unsupported:\n"
    "- A statement that the candidate does NOT have something, has not done "
    "something, or does not know someone. An absence needs no evidence, and "
    "flagging it tells the reader their honest 'no' looks like a fabrication.\n"
    "- A statement about the source material itself — 'my resume does not "
    "specify how long', 'that information isn't included here'. That describes "
    "the document, not the candidate.\n"
    "- Contact details, links, locations, salary figures, notice periods or "
    "availability that appear in the details the candidate provided. They "
    "supplied those directly; they are source material, not invention.\n"
    "- Filler with no factual content at all: 'N/A', 'Not applicable', an offer "
    "to provide more detail on request.\n\n"
    "Every flag costs the reader attention. A page where most answers are "
    "flagged teaches them to ignore the flags, which is worse than not flagging "
    "at all — so spend them only on something a candidate would be embarrassed "
    "to have said."
)


def structured_profile_block(profile: Profile) -> str:
    """The candidate's reliable, non-resume facts, for both prompts to read.

    Only fields the candidate actually filled in are listed: an absent field
    should read to the model as "not available" and produce an honest refusal,
    which is exactly what omitting it does. Listing every field as "not
    provided" would bury the ones that are.
    """
    lines = [
        f"Location: {profile.location or 'not provided'}",
        f"Years of professional experience: {profile.years_experience:g}",
    ]
    optional = (
        ("Notice period / when they can start", profile.notice_period),
        ("Current CTC", profile.current_ctc),
        ("Expected CTC", profile.expected_ctc),
        ("Preferred work locations", profile.preferred_locations),
        ("Work authorization", profile.work_authorization),
        ("LinkedIn profile", profile.linkedin_url),
        ("Portfolio / GitHub / personal site", profile.portfolio_url),
    )
    lines.extend(f"{label}: {value}" for label, value in optional if value)
    if profile.has_offer_in_hand is not None:
        answer = "yes" if profile.has_offer_in_hand else "no"
        lines.append(f"Currently holds another offer: {answer}")

    body = "\n".join(lines)
    # Worded so it still reads as English if the model echoes it. The previous
    # heading did not: an answer told an employer that a figure was "not
    # included in my resume or structured profile data", which is this system's
    # own vocabulary leaking onto a real application.
    return f"DETAILS THE CANDIDATE PROVIDED (authoritative — prefer over resume prose):\n{body}"


def grounding_source(profile: Profile) -> str:
    """Everything the candidate has actually told us, for the verifier to
    check against.

    The generator is told to use the structured fields, so a verifier that
    only sees the resume text flags the candidate's own location, links and
    salary as unsupported — the two prompts disagreeing about what counts as
    source material. Measured before fixing: a LinkedIn URL the candidate
    supplied himself came back flagged.
    """
    return (
        f"{structured_profile_block(profile)}\n\n"
        f"RESUME AND PROJECTS:\n{profile.full_resume_text}"
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
