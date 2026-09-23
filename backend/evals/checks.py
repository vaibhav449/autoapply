"""Deterministic checks for a generated application answer.

Each one encodes a failure that actually reached a real form during this
project, so the eval measures what has gone wrong before rather than what might
go wrong in theory. They are rules, not a second model: an LLM judging an LLM
brings its own nondeterminism and its own blind spots, and the point here is a
number that means the same thing on every run.

Three kinds of failure, kept apart because they cost different things:

- fabrication  — the answer asserts something about the candidate that their
                 material does not support. The one that can cost an offer.
- wrong_field  — it answers from the wrong fact: the employer's city as where
                 the candidate lives, the current salary as the expected one.
- form         — nothing false, but it does not read as the candidate talking:
                 Markdown, chatbot voice, talk about "the information provided".
"""

import re
from dataclasses import dataclass, field

FABRICATION = "fabrication"
WRONG_FIELD = "wrong_field"
FORM = "form"


@dataclass(frozen=True)
class CheckResult:
    check: str
    category: str
    passed: bool
    # The text that tripped the check, for the report. Empty when it passed.
    evidence: str = ""


# --- durations --------------------------------------------------------------

# A quantity directly in front of a unit of time: "1 year", "3+ years", "six
# months", "a couple of years". Deliberately not "many" — "I can't say how many
# years" is the honest answer this check exists to allow, not a claim.
_QUANTITY = (
    r"(?:\d+(?:\.\d+)?(?:\s*-\s*\d+)?\s*\+?"
    r"|a|an|one|two|three|four|five|six|seven|eight|nine|ten|twelve"
    r"|half an?|a few|a couple of|a couple|several)"
)
_DURATION = re.compile(rf"\b{_QUANTITY}\s*(?:years?|yrs?|months?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class NoDuration:
    """The answer must not state how long the candidate has done something.

    For questions whose answer the candidate's material does not contain. Seen
    live: "I have 1 year of experience with Python" for a resume that lists
    Python with no duration — the candidate's *total* experience, applied to
    one skill. The generation prompt forbids exactly this, and it still
    appeared on one run in two.
    """

    name: str = "no_duration"

    def evaluate(self, answer: str) -> CheckResult:
        match = _DURATION.search(answer)
        return CheckResult(
            self.name, FABRICATION, match is None, match.group(0) if match else ""
        )


# --- claims of experience the candidate does not have -----------------------

_NEGATION = re.compile(
    r"\b(?:not|no|never|without|none|neither|nor|lack|lacks|lacking|cannot)\b|n't\b",
    re.IGNORECASE,
)
# Where one claim ends and the next begins: sentence ends, a contrast ("..., but
# I have"), and a comma that opens a fresh first-person statement ("I don't list
# AWS, I deployed on AWS Lambda"). Plain commas are not boundaries, or a negated
# list — "I have not used Docker, Kubernetes, or AWS" — would lose its "not".
# Nor is "yet", which would cut "I have not yet used AWS" off from its "not".
_CLAUSE_BOUNDARY = re.compile(
    r"[.;!?]"
    r"|\b(?:but|however|although|though|while|whereas)\b"
    r"|,\s*(?=(?:I|I'\w+|my|My)\b)",
)


def _clauses(text: str) -> list[str]:
    return [part for part in _CLAUSE_BOUNDARY.split(text) if part.strip()]


# "Eager to learn PyTorch" says the candidate does not have it yet, as plainly
# as a "not" would. ("learned" is a claim, and is not matched.)
_WANTING = re.compile(r"\b(?:learn|learning|explore|exploring|pick up)\b", re.IGNORECASE)


def _presupposes(clause: str, term: str) -> bool:
    """The experience is taken as given and only a property of it is denied.
    Seen live: "The exact duration of my experience as an ML Engineer is not
    specified" — its "not" is about the duration, and the role it presupposes
    was never held.
    """
    return bool(
        re.search(
            r"\b(?:duration|length|extent|number of years|years)\s+of\s+(?:my\s+)?"
            rf"(?:experience|work|time)\s+(?:as|with|in|using|on)\s+(?:an?\s+)?"
            rf"{re.escape(term)}",
            clause,
            re.IGNORECASE,
        )
    )


@dataclass(frozen=True)
class Negates:
    """Every mention of something the candidate has no experience with must sit
    in a clause that denies it.

    "I do not have experience with AWS" and "PyTorch isn't a tool I've worked
    with" both pass; "I have deployed on AWS" fails. A denial of something
    *about* the experience does not count — "the duration of my experience as
    an ML Engineer is not specified" presupposes the role. An answer that never
    names the term passes, since it claims nothing.

    Known blind spot: a clause that contains a denial and a claim of the same
    thing — "I have not only used AWS but led the migration" — reads as denied.
    The grounding check is measured alongside for exactly that kind of gap.
    """

    terms: tuple[str, ...]
    name: str = "negates"

    def evaluate(self, answer: str) -> CheckResult:
        for clause in _clauses(answer):
            for term in self.terms:
                if not re.search(rf"\b{re.escape(term)}", clause, re.IGNORECASE):
                    continue
                denied = _NEGATION.search(clause) or _WANTING.search(clause)
                if not denied or _presupposes(clause, term):
                    return CheckResult(self.name, FABRICATION, False, clause.strip())
        return CheckResult(self.name, FABRICATION, True)


# --- content a question does or does not allow ------------------------------


@dataclass(frozen=True)
class Forbid:
    """None of these may appear. For facts the answer must not state: the
    employer's city given as the candidate's, an invented profile URL, a
    work-authorization status the candidate never supplied.
    """

    patterns: tuple[str, ...]
    category: str
    name: str = "forbid"

    def evaluate(self, answer: str) -> CheckResult:
        for pattern in self.patterns:
            match = re.search(pattern, answer, re.IGNORECASE)
            if match:
                return CheckResult(self.name, self.category, False, match.group(0))
        return CheckResult(self.name, self.category, True)


@dataclass(frozen=True)
class Require:
    """At least one of these must appear — the fact the question asks for,
    when the candidate supplied it.
    """

    patterns: tuple[str, ...]
    category: str
    name: str = "require"

    def evaluate(self, answer: str) -> CheckResult:
        if any(re.search(pattern, answer, re.IGNORECASE) for pattern in self.patterns):
            return CheckResult(self.name, self.category, True)
        return CheckResult(self.name, self.category, False, answer[:80])


@dataclass(frozen=True)
class Fits:
    """The answer fits the field it is going into (see generate_draft_answer)."""

    max_length: int
    name: str = "fits"

    def evaluate(self, answer: str) -> CheckResult:
        passed = len(answer) <= self.max_length
        return CheckResult(
            self.name, FORM, passed, "" if passed else f"{len(answer)} > {self.max_length}"
        )


# --- the voice every answer must have ---------------------------------------


@dataclass(frozen=True)
class _PatternCheck:
    name: str
    patterns: tuple[str, ...] = field(default=())

    def evaluate(self, answer: str) -> CheckResult:
        for pattern in self.patterns:
            match = re.search(pattern, answer, re.IGNORECASE | re.MULTILINE)
            if match:
                return CheckResult(self.name, FORM, False, match.group(0))
        return CheckResult(self.name, FORM, True)


# The form field is plain text; Markdown arrives as literal brackets and stars.
# Seen live: a LinkedIn answer written as [LinkedIn](https://...).
NO_MARKDOWN = _PatternCheck(
    "no_markdown",
    (
        r"\[[^\]]+\]\([^)]+\)",  # [text](url)
        r"\*\*|__",  # bold
        r"^\s*[-*•]\s",  # bullet list
        r"^#{1,6}\s",  # heading
    ),
)

# An assistant addressing whoever prompted it, not a candidate addressing an
# employer. Seen live: "Please let me know if you need any additional details or
# if there's another way I can assist with this application."
NO_ASSISTANT_VOICE = _PatternCheck(
    "no_assistant_voice",
    (
        r"\blet me know\b",
        r"\bhappy to help\b",
        r"\bfeel free to\b",
        r"\bhope this helps\b",
        r"\bas an ai\b",
        r"\bI can (?:assist|help) (?:you|with)\b",
        r"\banother way I can\b",
    ),
)

# This system's own vocabulary reaching an employer. Seen live, twice: "not
# specified in the information provided" (still on a real form at the time of
# writing) and "not included in my resume or structured profile data". A
# candidate saying their resume does not state something is fine — the
# employer has the resume. "The information provided" is not something a
# candidate has; it is what the model was handed.
NO_SOURCE_TALK = _PatternCheck(
    "no_source_talk",
    (
        r"\b(?:in|from|with|by) the (?:information|details|data) (?:provided|given|available)\b",
        r"\bprofile (?:data|field|information)\b",
        r"\bstructured (?:data|field|profile)\b",
        r"\bdata block\b",
        r"\bthe candidate\b",
    ),
)

EVERY_ANSWER = (NO_MARKDOWN, NO_ASSISTANT_VOICE, NO_SOURCE_TALK)
