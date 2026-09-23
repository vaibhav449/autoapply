import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.draft_answer import DraftAnswer
from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.llm_gateway import openai_client
from app.services.tailoring.grounding import (
    VERIFICATION_VERSION,
    grounding_source,
    structured_profile_block,
    verify_grounding,
)

GENERATION_SYSTEM_PROMPT = (
    "Write a concise, first-person answer to this job application question, for the "
    "candidate below applying to the specific job described. Ground every claim "
    "strictly in the candidate's real resume and project content — never invent "
    "experience, skills, metrics, or achievements not present in that content.\n\n"
    "The DETAILS THE CANDIDATE PROVIDED block is given separately from the "
    "resume text and is "
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
    "relevant (e.g. a LinkedIn or GitHub question), write the bare URL on its own.\n\n"
    "Never describe where your information came from. An employer reads this "
    "answer and has no idea what a profile field or a data block is.\n\n"
    "Answer the question that was asked, in its own terms. Read the question "
    "first and name the thing it is about: if it asks who someone is, the "
    "answer is about that person; if it asks for an amount, about the amount; "
    "if it asks where, about the place. When the information is not available, "
    "say that about the thing actually asked and nothing else. An answer that "
    "would fit some other question is wrong even when it is honest — this is "
    "worth re-reading the question for, because both failures have happened on "
    "real applications."
)


# Bump whenever a generation prompt changes. It feeds the cache fingerprint, so
# raising it regenerates every stored answer — without this, improving a prompt
# left every already-cached answer exactly as it was, which is how a fixed
# hallucination kept being served from a row written before the fix.
#
# "4": blank candidate fields are listed as "not provided" instead of left out,
# and total experience is labelled as a total (structured_profile_block).
# Cached answers written under "3" can hold exactly what that fixed — an
# invented sponsorship status or salary expectation.
#
# "5": "4" also extended the duration rule above to say a total never answers a
# per-skill question. It stopped some invented per-skill durations and started
# something worse: on a real profile with no AWS in it, "Exp working with AWS?"
# came back "The exact duration of my experience working with AWS is not
# specified. However, I have utilized AWS in my projects" 8 times out of 8,
# against 0 of 8 with the rule as it was. The rule is back to that; anything
# generated under "4" may carry the invented claim and must not be reused.
GENERATION_VERSION = "5"


def answer_fingerprint(profile: Profile, job: JobModel) -> str:
    """Identifies everything a generated answer depends on besides its question.

    The question is already the cache key, so what is left is the prompt logic
    and the material it was grounded in — edit the resume and the old answer is
    describing a person who no longer exists on paper.
    """
    payload = "\0".join(
        [
            GENERATION_VERSION,
            # The row stores the grounding check's flags as well as the text, so
            # they go stale when that check changes even though the answer does not.
            VERIFICATION_VERSION,
            profile.full_resume_text,
            job.description or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _is_reusable(existing: DraftAnswer, fingerprint: str, max_length: int | None = None) -> bool:
    """A NULL fingerprint means a person wrote this answer, so it is theirs and
    stays put however far the prompt has moved on — even when it is too long for
    the field in front of it, which the fill then leaves for them rather than
    rewriting their words. Anything else is ours, and is only reusable while it
    still matches what it would be generated from now and fits where it is going.

    The limit is not part of the fingerprint on purpose. An answer that fits is
    a good answer whatever it was generated under, so the "Generate answer"
    button (which knows no field) and a fill (which does) settle on the same
    row instead of regenerating over each other on every visit.
    """
    if existing.fingerprint is None:
        return True
    if existing.fingerprint != fingerprint:
        return False
    return max_length is None or len(existing.answer_text) <= max_length



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
    "Work authorization and visa questions are answerable ONLY from the "
    "structured work authorization field. Where the candidate lives, studied or "
    "holds citizenship does not establish whether they need sponsorship in some "
    "other country, and inferring one from the other is how an application ends "
    "up carrying a false statement about immigration status. If that field is "
    "absent, reply NONE however obvious the answer looks — observed live: asked "
    "twice about US sponsorship with nothing on file, the same model answered "
    "'Yes' and then 'No' on the same application.\n\n"
    "But an option that explicitly covers having none or little of something "
    "(\"No/Limited Experience\", \"None\", \"0 years\", \"No\") IS the grounded "
    "answer when the candidate's material shows they do not have it — that is "
    "what such an option exists for. Do not reply NONE just because the resume "
    "never mentions the thing being asked about; if it is an experience or skill "
    "the resume would have listed had they had it, its absence is the answer.\n\n"
    "The DETAILS THE CANDIDATE PROVIDED block is authoritative — prefer it over inferring the "
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


# A shortening rewrite aims comfortably under the field's limit rather than at
# it: aim at the line and a fair share of rewrites land just over.
LENGTH_TARGET_RATIO = 0.85


async def _complete(messages: list[dict[str, str]]) -> str:
    completion = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        # Deterministic on purpose, same reasoning as job-requirements extraction:
        # ensure_draft_answer caches the result permanently, so sampling variance
        # would freeze one unlucky answer onto the row forever.
        temperature=0,
        messages=messages,
    )
    content = completion.choices[0].message.content
    if content is None:
        raise ValueError("LLM returned no content for draft answer generation.")
    return content


async def generate_draft_answer(
    profile: Profile, job: JobModel, question_text: str, max_length: int | None = None
) -> str:
    """max_length is the form field's own character limit, when known.

    The first request never mentions it. Measured on six real questions:
    stating the limit up front — even framed as a ceiling — made short answers
    grow filler toward it (one plain 42-character answer became 150), and made
    long ones get trimmed from the end, which is where the sentence answering a
    "how many years" question happened to sit. Asked plainly, the model puts
    the right content in and only sometimes too much of it.

    So an answer that fits is exactly what it would have been with no limit at
    all, and one that does not gets a single rewrite, done from the complete
    answer so the model can see what the question needs kept. One, not a loop:
    what still will not fit after that is left for the human, never cut to size
    here. Either way verify_grounding checks the final text like any other.
    """
    messages = [
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
    ]
    content = await _complete(messages)

    if max_length is not None and len(content) > max_length:
        target = int(max_length * LENGTH_TARGET_RATIO)
        content = await _complete(
            [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        f"That answer is {len(content)} characters, and the form field "
                        f"holds at most {max_length} — anything longer is cut off "
                        f"mid-sentence. Rewrite it in under {target} characters. Keep "
                        f"what directly answers the question as asked, cut supporting "
                        f"detail first, and add nothing it does not already say."
                    ),
                },
            ]
        )

    return content


async def ensure_draft_answer(
    application: Application,
    profile: Profile,
    job: JobModel,
    question_text: str,
    db: AsyncSession,
    max_length: int | None = None,
) -> DraftAnswer:
    """Generate once per (application, question), and again whenever what it was
    generated from has moved on — or when the field it is going into cannot hold
    it (max_length, when the caller knows the field).

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
    if existing is not None and _is_reusable(existing, fingerprint, max_length):
        return existing

    content = await generate_draft_answer(profile, job, question_text, max_length)
    # A draft answer, unlike a cover letter, is often pasted into a form field
    # near-verbatim rather than read and rewritten first — that raises the cost of
    # an unflagged hallucination, so this artifact gets the verification pass.
    verification = await verify_grounding(content, grounding_source(profile))

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
