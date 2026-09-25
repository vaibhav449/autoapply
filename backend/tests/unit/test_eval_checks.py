"""The eval's rules, pinned to the real answers they were written for.

Every "seen live" string below was produced by the draft-answer generator on a
real application during this project. If a rule stops catching one of them, the
eval has quietly stopped measuring the failure it exists for.
"""

import pytest

from evals.checks import (
    FABRICATION,
    FORM,
    NO_ASSISTANT_VOICE,
    NO_MARKDOWN,
    NO_SOURCE_TALK,
    WRONG_FIELD,
    Fits,
    Forbid,
    Negates,
    NoDuration,
    Require,
)

# --- NoDuration --------------------------------------------------------------


def test_an_inferred_skill_duration_is_caught() -> None:
    seen_live = "I have 1 year of experience with Python, as indicated in my resume."

    result = NoDuration().evaluate(seen_live)

    assert result.passed is False
    assert result.category == FABRICATION
    assert result.evidence == "1 year"


@pytest.mark.parametrize(
    "answer",
    [
        "Around two years in total.",
        "3+ years of professional Python.",
        "About 1.5 years.",
        "Six months on the team.",
        "A couple of years, mostly backend.",
        "Roughly a year.",
    ],
)
def test_every_way_of_stating_a_duration_is_caught(answer: str) -> None:
    assert NoDuration().evaluate(answer).passed is False


@pytest.mark.parametrize(
    "answer",
    [
        # seen live — the honest answer this rule exists to allow
        (
            "The exact duration of my experience with Python isn't specified in my "
            "resume, but I have utilized Python in various projects."
        ),
        # seen live — "number of years" is not a number of years
        (
            "I have experience with React as part of my role as a Full-Stack Developer "
            "Intern, but the exact number of years of experience with React is not "
            "specified in my resume."
        ),
        "I can't say how many years exactly.",
    ],
)
def test_saying_the_duration_is_not_stated_passes(answer: str) -> None:
    assert NoDuration().evaluate(answer).passed is True


# --- Negates -----------------------------------------------------------------


def test_a_presupposed_role_is_caught_even_with_a_not_in_the_sentence() -> None:
    """Seen live. The "not" is there, but after the role — the sentence still
    takes for granted that the candidate was an ML Engineer."""
    seen_live = (
        "The exact duration of my experience as an ML Engineer is not specified, but I "
        "have worked on AI and LLM projects during my internship."
    )

    result = Negates(("ML Engineer",)).evaluate(seen_live)

    assert result.passed is False
    assert "ML Engineer" in result.evidence


def test_denying_the_role_passes() -> None:
    seen_live = (
        "I have 1 year of experience as a Full-Stack Developer with a focus on AI and "
        "LLM technologies. However, I do not have specific experience as a dedicated "
        "ML Engineer."
    )

    assert Negates(("ML Engineer",)).evaluate(seen_live).passed is True


@pytest.mark.parametrize(
    "answer",
    [
        "My resume does not specify any experience working with AWS.",  # seen live
        "I do not have experience working with AWS.",  # seen live
        "I have not used Docker, Kubernetes, or AWS.",  # a negated list keeps its "not"
        "I have not yet worked with AWS.",
        "I haven't used AWS, but I have deployed apps on Render.",
        "That's not something I have hands-on time with.",  # never names it
        "AWS isn't something I've worked with.",  # the denial can come after
        "I haven't used AWS, but I'm eager to learn AWS at Acme.",
    ],
)
def test_an_honest_no_passes(answer: str) -> None:
    assert Negates(("AWS",)).evaluate(answer).passed is True


@pytest.mark.parametrize(
    "answer",
    [
        "I have deployed several services on AWS.",
        "I have used AWS, though not in production.",
        "I haven't used Azure, but I have used AWS Lambda.",
        "I don't list it on my resume, I have deployed apps on AWS Lambda.",
        "I learned AWS through a certification course.",  # "learned" is a claim
        "The number of years of my experience with AWS is not stated.",  # presupposed
    ],
)
def test_a_claim_of_it_is_caught(answer: str) -> None:
    assert Negates(("AWS",)).evaluate(answer).passed is False


def test_the_why_us_patterns_separate_the_company_from_the_candidate() -> None:
    from evals.datasets.draft_answers import CASES

    why_us = next(case for case in CASES if case.id == "why-us")
    [check] = why_us.checks

    honest = (
        "I'm drawn to Acme's work for banking clients, and I'd like to grow into "
        "PyTorch and AWS alongside a team that uses them daily."
    )
    borrowed = "My experience with PyTorch makes me a strong fit for Acme."

    assert check.evaluate(honest).passed is True
    assert check.evaluate(borrowed).passed is False


# --- Forbid / Require / Fits -------------------------------------------------


def test_forbid_reports_its_own_category() -> None:
    result = Forbid((r"\bPune\b",), WRONG_FIELD).evaluate("I live in Pune.")

    assert result.passed is False
    assert result.category == WRONG_FIELD
    assert result.evidence == "Pune"


def test_require_needs_one_of_its_patterns() -> None:
    check = Require((r"\bJaipur\b",), WRONG_FIELD)

    assert check.evaluate("I'm based in Jaipur, Rajasthan.").passed is True
    assert check.evaluate("I'm based in Pune.").passed is False


def test_fits_is_measured_in_characters() -> None:
    assert Fits(10).evaluate("x" * 10).passed is True
    result = Fits(10).evaluate("x" * 11)
    assert result.passed is False
    assert result.category == FORM


# --- the voice every answer must have ----------------------------------------


def test_chatbot_voice_is_caught() -> None:
    seen_live = (
        "My expected CTC is not specified in the information provided. Please let me "
        "know if you need any additional details or if there's another way I can "
        "assist with this application."
    )

    assert NO_ASSISTANT_VOICE.evaluate(seen_live).passed is False


@pytest.mark.parametrize(
    "seen_live",
    [
        "My expected CTC is not specified in the information provided.",
        "That figure is not included in my resume or structured profile data.",
    ],
)
def test_the_systems_own_vocabulary_is_caught(seen_live: str) -> None:
    assert NO_SOURCE_TALK.evaluate(seen_live).passed is False


def test_a_candidate_referring_to_their_own_resume_is_fine() -> None:
    """The employer has the resume; saying it does not state something is a
    sentence a candidate could write."""
    answer = "The exact duration isn't specified in my resume."

    assert NO_SOURCE_TALK.evaluate(answer).passed is True


def test_markdown_is_caught_and_a_bare_url_is_not() -> None:
    seen_live = "[LinkedIn](https://linkedin.com/in/example)"

    assert NO_MARKDOWN.evaluate(seen_live).passed is False
    assert NO_MARKDOWN.evaluate("https://linkedin.com/in/example").passed is True


def test_left_for_candidate_judges_both_directions() -> None:
    """Uses the pipeline's own detector, so the eval scores exactly what
    decides whether a field gets filled."""
    from evals.checks import COVERAGE, LeftForCandidate

    should_leave = LeftForCandidate(expected=True)
    assert should_leave.evaluate("NOT_PROVIDED").passed is True
    assert should_leave.evaluate("not provided").passed is True  # echoed wording
    placeholder = should_leave.evaluate("I do not have information regarding visa sponsorship.")
    assert placeholder.passed is False
    assert placeholder.category == FORM

    should_answer = LeftForCandidate(expected=False)
    assert should_answer.evaluate("I do not have experience working with AWS.").passed is True
    left_blank = should_answer.evaluate("NOT_PROVIDED")
    assert left_blank.passed is False
    assert left_blank.category == COVERAGE


def test_the_dropdown_judge_separates_false_statements_from_off_contract_picks() -> None:
    from evals.datasets.dropdowns import CASES
    from evals.dropdowns import FALSE, OFF, OK, judge

    by_id = {case.id: case for case in CASES}
    india_only = by_id["us-sponsorship-india-only"]
    assert judge(india_only, None) == OK  # left for the candidate
    assert judge(india_only, "No") == FALSE  # the invented status, seen live
    assert judge(india_only, "Yes") == OFF  # a guess the details do not support either

    notice = by_id["notice-vague"]
    assert judge(notice, "Currently not working") == FALSE  # seen live, for an intern
    assert judge(notice, "≤30 Days - Negotiable") == OK


def test_every_dropdown_label_is_one_of_the_questions_own_options() -> None:
    """A label naming an option the form never offers can never be picked,
    so it would silently test nothing."""
    from evals.datasets.dropdowns import CASES

    for case in CASES:
        assert (case.acceptable | case.false_picks) - {None} <= set(case.options), case.id
