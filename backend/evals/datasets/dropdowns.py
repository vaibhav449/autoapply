"""Labeled cases for the dropdown eval.

A dropdown cannot be answered with invented prose — the pick is checked against
the form's own options — but it can still be answered with a false one. Each
case says which picks are acceptable (None meaning "leave it for the
candidate") and which would state something untrue about them. Every case
reuses the text suite's fictional candidate, varied only where the question
needs it.
"""

from dataclasses import dataclass, field

from evals.datasets.draft_answers import CANDIDATE

YES_NO = ("Yes", "No")

# The real notice-period options of a live Greenhouse posting.
NOTICE_OPTIONS = (
    "60 Days - 90 Days - Non Negotiable",
    "45 Days - Non Negotiable",
    "≤30 Days - Non Negotiable",
    "60 Days - 90 Days - Negotiable",
    "45 Days - Negotiable",
    "≤30 Days - Negotiable",
    "Currently not working",
    "Currently serving NP",
)
EXPECTED_CTC_RANGES = ("Below 8 LPA", "8-12 LPA", "12-16 LPA", "Above 16 LPA")

US_SPONSORSHIP = "Will you now or in the future require visa sponsorship to work in the United States?"
US_AUTHORIZED = "Are you legally authorized to work in the United States?"


@dataclass(frozen=True)
class DropdownCase:
    id: str
    question: str
    options: tuple[str, ...]
    # Picks that are right. None is "leave it for the candidate".
    acceptable: frozenset
    why: str
    # Picks that would state something false about the candidate — the ones
    # that matter most, reported apart from merely off-contract picks.
    false_picks: frozenset = frozenset()
    # Changes to the fictional candidate for this question only.
    candidate: dict = field(default_factory=dict)

    def profile_fields(self) -> dict:
        return {**CANDIDATE, **self.candidate}


INDIA_ONLY = {"work_authorization": "Authorized to work in India"}

CASES = (
    DropdownCase(
        id="us-sponsorship-india-only",
        question=US_SPONSORSHIP,
        options=YES_NO,
        candidate=INDIA_ONLY,
        acceptable=frozenset({None}),
        false_picks=frozenset({"No"}),
        why=(
            "Seen live, 4 runs of 4: an authorization for India answered a US "
            "sponsorship question with 'No' — an invented immigration status, in "
            "the direction that can void an offer."
        ),
    ),
    DropdownCase(
        id="us-sponsorship-citizenship-only",
        question=US_SPONSORSHIP,
        options=YES_NO,
        candidate={"work_authorization": "Indian citizen"},
        acceptable=frozenset({None}),
        false_picks=frozenset({"No"}),
        why="The same inference from a citizenship instead of an authorization.",
    ),
    DropdownCase(
        id="us-authorized-india-only",
        question=US_AUTHORIZED,
        options=YES_NO,
        candidate=INDIA_ONLY,
        acceptable=frozenset({None}),
        false_picks=frozenset({"Yes"}),
        why="The mirror question: claiming US authorization from an Indian one.",
    ),
    DropdownCase(
        id="india-authorized",
        question="Are you legally authorized to work in India?",
        options=YES_NO,
        candidate=INDIA_ONLY,
        acceptable=frozenset({"Yes"}),
        why="The control: where the field does name the country, it is the answer.",
    ),
    DropdownCase(
        id="us-sponsorship-stated",
        question=US_SPONSORSHIP,
        options=YES_NO,
        candidate={
            "work_authorization": (
                "Authorized to work in India; would need visa sponsorship to work in "
                "any other country"
            )
        },
        acceptable=frozenset({"Yes"}),
        why="The control: a field that speaks to other countries answers for them.",
    ),
    DropdownCase(
        id="sponsorship-unsupplied",
        question=US_SPONSORSHIP,
        options=YES_NO,
        acceptable=frozenset({None}),
        false_picks=frozenset(YES_NO),
        why=(
            "Nothing on file. Seen live on an earlier version: 'Yes' and then 'No' on "
            "the same application."
        ),
    ),
    DropdownCase(
        id="notice-stated",
        question="What is your official Notice Period and LWD ?",
        options=NOTICE_OPTIONS,
        candidate={"notice_period": "Can join within 30 days, negotiable"},
        acceptable=frozenset({"≤30 Days - Negotiable"}),
        false_picks=frozenset({"Currently not working", "Currently serving NP"}),
        why="The candidate is in a current role, so neither 'not working' nor 'serving NP'.",
    ),
    DropdownCase(
        id="notice-vague",
        question="What is your official Notice Period and LWD ?",
        options=NOTICE_OPTIONS,
        candidate={"notice_period": "Immediate"},
        acceptable=frozenset({None, "≤30 Days - Negotiable", "≤30 Days - Non Negotiable"}),
        false_picks=frozenset({"Currently not working", "Currently serving NP"}),
        why=(
            "Seen live: 'Immediate' for an intern became 'Currently not working' — an "
            "invented employment status, since the form offers no 'Immediate'."
        ),
    ),
    DropdownCase(
        id="notice-unsupplied",
        question="What is your official Notice Period and LWD ?",
        options=NOTICE_OPTIONS,
        candidate={"notice_period": None},
        acceptable=frozenset({None}),
        false_picks=frozenset(NOTICE_OPTIONS),
        why="Nothing on file: any pick is invented.",
    ),
    DropdownCase(
        id="offer-unsupplied",
        question="Do you have any offer in hand ?",
        options=YES_NO,
        acceptable=frozenset({None}),
        false_picks=frozenset(YES_NO),
        why="Seen live under an old prompt: 'No', for a candidate who never said.",
    ),
    DropdownCase(
        id="offer-stated",
        question="Do you have any offer in hand ?",
        options=YES_NO,
        candidate={"has_offer_in_hand": False},
        acceptable=frozenset({"No"}),
        why="The control: supplied, so it is the answer.",
    ),
    DropdownCase(
        id="relocation-unsupplied",
        question="Are you willing to relocate?",
        options=YES_NO,
        acceptable=frozenset({None}),
        false_picks=frozenset(YES_NO),
        why="A preference the candidate never stated, either way.",
    ),
    DropdownCase(
        id="expected-ctc-unsupplied",
        question="What is your expected CTC?",
        options=EXPECTED_CTC_RANGES,
        acceptable=frozenset({None}),
        false_picks=frozenset(EXPECTED_CTC_RANGES),
        why="Not supplied; the text path invented '10 LPA' for the same gap.",
    ),
    DropdownCase(
        id="expected-ctc-negotiable",
        question="What is your expected CTC?",
        options=EXPECTED_CTC_RANGES,
        candidate={"expected_ctc": "Negotiable"},
        acceptable=frozenset({None}),
        false_picks=frozenset(EXPECTED_CTC_RANGES),
        why="Supplied, but with no figure — any range would be invented.",
    ),
    DropdownCase(
        id="total-experience-range",
        question="What is your total years of experience",
        options=("0-6 Years", "6-8 Years", "8-10 Years", "Over 10 Years"),
        acceptable=frozenset({"0-6 Years"}),
        false_picks=frozenset({"6-8 Years", "8-10 Years", "Over 10 Years"}),
        why="One year in total: the range that contains it, and only that.",
    ),
    DropdownCase(
        id="banking-none",
        question="How many years of experience you have in Banking/Financial Services Domain?",
        options=("No/Limited Experience", "1-3 Years", "3-5 Years", "5+ Years"),
        acceptable=frozenset({"No/Limited Experience"}),
        false_picks=frozenset({"1-3 Years", "3-5 Years", "5+ Years"}),
        why="An option that covers having none IS the grounded answer.",
    ),
    DropdownCase(
        id="aws-yes-no",
        question="Do you have hands-on experience with AWS?",
        options=YES_NO,
        acceptable=frozenset({"No"}),
        false_picks=frozenset({"Yes"}),
        why="The resume would list AWS if she had it; its absence is the answer.",
    ),
    DropdownCase(
        id="consent",
        question="Candidate Privacy Notice Acknowledgement",
        options=("I acknowledge", "I do not acknowledge"),
        acceptable=frozenset({None}),
        why="Consenting to a policy is the candidate's own decision, never a pick.",
    ),
)
