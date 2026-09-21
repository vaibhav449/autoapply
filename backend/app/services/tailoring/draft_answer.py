import hashlib

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
    "experience, skills, metrics, or achievements not present in that content.\n\n"
    "STRUCTURED PROFILE DATA is given separately from the resume text and is "
    "authoritative — prefer it over inferring the same fact from resume prose. In "
    "particular: a city named as an employer's or school's address in the resume is "
    "NOT the candidate's own location. Use the structured location field for "
    "questions about where the candidate is, lives, or is based.\n\n"
    "Each structured field answers only its own question. Current CTC and expected "
    "CTC are different questions, and so are where the candidate currently lives and "
    "where they want to work. If the field a question actually asks about is missing, "
    "say that plainly — never answer it with a different field's value.\n\n"
    "Never calculate or infer a duration. If the resume does not explicitly state how "
    "long the candidate has done something, say the exact duration isn't specified — "
    "do not infer a start date from surrounding context and compute years from it.\n\n"
    "An ongoing role dated through the present (e.g. an internship marked "
    "'... - Present') is real, current experience — never claim 'no experience' or "
    "'not currently working' when one is listed. For questions specifically about a "
    "formal notice period, you may note that an internship doesn't carry the same "
    "notice obligations as full-time employment, but do not claim to be unemployed "
    "while an internship is active.\n\n"
    "Some questions ask about things a resume cannot answer — notice period, "
    "salary expectations, work authorization, another offer in hand, where the "
    "candidate wants to work. The candidate supplies these separately in the "
    "structured data above; when it answers the question, use it directly and "
    "state it plainly.\n\n"
    "Whenever the candidate's material — resume, projects and structured data "
    "together — does not address what the question asks, write a short honest "
    "placeholder saying so instead of inventing a plausible answer. Never claim "
    "experience with a technology, tool, platform or domain that does not appear "
    "in that material, and never invent a figure, date or status. Naming a "
    "different tool the candidate has actually used is fine, but do not present "
    "it as experience with the one being asked about. This draft is reviewed by "
    "the candidate before anything is submitted.\n\n"
    "This answer is typed verbatim into a plain-text field on a real application "
    "form — it is never rendered as Markdown or HTML. Write plain text only: no "
    "[link](url) syntax, no *emphasis*, no headings or bullet lists. If a URL is "
    "relevant (e.g. a LinkedIn or GitHub question), write the bare URL on its own."
)


# Bump whenever a generation prompt changes. It feeds the cache fingerprint, so
# raising it regenerates every stored answer — without this, improving a prompt
# left every already-cached answer exactly as it was, which is how a fixed
# hallucination kept being served from a row written before the fix.
GENERATION_VERSION = "1"


def answer_fingerprint(profile: Profile, job: JobModel) -> str:
    """Identifies everything a generated answer depends on besides its question.

    The question is already the cache key, so what is left is the prompt logic
    and the material it was grounded in — edit the resume and the old answer is
    describing a person who no longer exists on paper.
    """
    payload = "\0".join(
        [GENERATION_VERSION, profile.full_resume_text, job.description or ""]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _is_reusable(existing: DraftAnswer, fingerprint: str) -> bool:
    """A NULL fingerprint means a person wrote this answer, so it is theirs and
    stays put however far the prompt has moved on. Anything else is ours, and is
    only reusable while it still matches what it would be generated from now.
    """
    return existing.fingerprint is None or existing.fingerprint == fingerprint


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
    return f"STRUCTURED PROFILE DATA (authoritative — prefer over resume prose):\n{body}"


CHOICE_SYSTEM_PROMPT = (
    "Pick the single best option from a fixed dropdown list on a real job "
    "application form, for the candidate described below.\n\n"
    "Reply with EXACTLY one option copied verbatim from the list, or the single "
    "word NONE. Never write anything else — no explanation, no punctuation, no "
    "option that is not on the list.\n\n"
    "Reply NONE when the candidate's material genuinely cannot answer the "
    "question, or when it asks the candidate to consent to or acknowledge a "
    "policy. A wrong pick on a real application is worse than leaving it for the "
    "human to choose.\n\n"
    "Notice period, salary, work authorization and another offer in hand are "
    "supplied as structured data when the candidate has given them. If the "
    "structured data above answers the question, pick the option matching it "
    "rather than replying NONE; if it is absent, reply NONE.\n\n"
    "But an option that explicitly covers having none or little of something "
    "(\"No/Limited Experience\", \"None\", \"0 years\", \"No\") IS the grounded "
    "answer when the candidate's material shows they do not have it — that is "
    "what such an option exists for. Do not reply NONE just because the resume "
    "never mentions the thing being asked about; if it is an experience or skill "
    "the resume would have listed had they had it, its absence is the answer.\n\n"
    "STRUCTURED PROFILE DATA is authoritative — prefer it over inferring the "
    "same fact from resume prose. Never invent experience the candidate does not "
    "have. An ongoing role dated through the present (e.g. an internship marked "
    "'... - Present') is real, current experience — do not treat the candidate "
    "as having none. Where the options are experience ranges, pick the range "
    "that contains the candidate's actual years of experience."
)


async def choose_draft_option(
    profile: Profile, job: JobModel, question_text: str, options: list[str]
) -> str | None:
    """Pick one of a dropdown's real options, or None to leave it for the human.

    Structurally safer than free-text generation: the return value is checked
    against the list the live form actually offered, so a hallucinated value
    cannot reach the form at all — the worst case is an honest skip.
    """
    numbered = "\n".join(f"- {option}" for option in options)
    completion = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": CHOICE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{structured_profile_block(profile)}\n\n"
                    f"CANDIDATE RESUME AND PROJECTS:\n{profile.full_resume_text}\n\n"
                    f"JOB: {job.title} at {job.company}\n\n"
                    f"APPLICATION QUESTION:\n{question_text}\n\n"
                    f"OPTIONS:\n{numbered}"
                ),
            },
        ],
    )
    content = completion.choices[0].message.content
    if content is None:
        return None

    choice = content.strip()
    # The hard gate: anything that is not one of this form's own options is
    # treated as a refusal, including "NONE" and any near-miss paraphrase.
    return choice if choice in options else None


async def ensure_draft_option(
    application: Application,
    profile: Profile,
    job: JobModel,
    question_text: str,
    options: list[str],
    db: AsyncSession,
) -> str | None:
    """Cache-once per (application, question), same as ensure_draft_answer, so a
    retried fill re-selects the same option instead of paying for a fresh choice.

    A refusal is deliberately not cached: it costs one small call to re-ask, and
    a row with no answer would render as an empty draft answer in the UI.

    A stored choice is also dropped once it is no longer one of the options this
    form offers, which covers a form being edited under a cached answer.
    """
    fingerprint = answer_fingerprint(profile, job)
    result = await db.execute(
        select(DraftAnswer).where(
            DraftAnswer.application_id == application.id,
            DraftAnswer.question_text == question_text,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None and _is_reusable(existing, fingerprint):
        return existing.answer_text if existing.answer_text in options else None

    choice = await choose_draft_option(profile, job, question_text, options)
    if choice is None:
        return None

    if existing is not None:
        existing.answer_text = choice
        existing.unverified_claims = []
        existing.fingerprint = fingerprint
        await db.commit()
        return choice

    # No grounding pass here, unlike a free-text answer: the value is one of the
    # form's own options, so there is no invented prose for verify_grounding to
    # check — the option list is itself the constraint.
    db.add(
        DraftAnswer(
            application_id=application.id,
            question_text=question_text,
            answer_text=choice,
            unverified_claims=[],
            fingerprint=fingerprint,
        )
    )
    await db.commit()
    return choice


async def generate_draft_answer(profile: Profile, job: JobModel, question_text: str) -> str:
    completion = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        # Deterministic on purpose, same reasoning as job-requirements extraction:
        # ensure_draft_answer caches the result permanently, so sampling variance
        # would freeze one unlucky answer onto the row forever.
        temperature=0,
        messages=[
            {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{structured_profile_block(profile)}\n\n"
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
    """Generate once per (application, question), and again whenever what it was
    generated from has moved on.

    Caching on the question alone is what let a fixed hallucination keep being
    served: the prompt was corrected, but every answer written before the fix
    stayed exactly as it was, because a plain cache hit never looks at whether
    the thing that produced it still exists. An answer a person edited is the
    one exception — that is theirs, and no prompt change reclaims it.
    """
    fingerprint = answer_fingerprint(profile, job)
    result = await db.execute(
        select(DraftAnswer).where(
            DraftAnswer.application_id == application.id,
            DraftAnswer.question_text == question_text,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None and _is_reusable(existing, fingerprint):
        return existing

    content = await generate_draft_answer(profile, job, question_text)
    # A draft answer, unlike a cover letter, is often pasted into a form field
    # near-verbatim rather than read and rewritten first — that raises the cost of
    # an unflagged hallucination, so this artifact gets the verification pass.
    verification = await verify_grounding(content, profile.full_resume_text)

    if existing is not None:
        # Updated in place rather than replaced: (application, question) is
        # unique, and anything already pointing at this row should follow the
        # answer rather than the id.
        existing.answer_text = content
        existing.unverified_claims = verification.unverified_claims
        existing.fingerprint = fingerprint
        await db.commit()
        return existing

    draft_answer = DraftAnswer(
        application_id=application.id,
        question_text=question_text,
        answer_text=content,
        unverified_claims=verification.unverified_claims,
        fingerprint=fingerprint,
    )
    db.add(draft_answer)
    await db.commit()
    return draft_answer
