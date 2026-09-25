"""The draft-answer eval: how often does the generator put something false,
misattributed, or off-voice into an answer headed for a real form?

    cd backend
    python -m evals.run_eval draft_answers --runs 5

Drives the real generator and the real grounding check, so it needs
OPENAI_API_KEY and costs a few cents a run — which is why it is run by hand
rather than in CI. The rules that judge each answer are deterministic and have
their own unit tests (tests/unit/test_eval_checks.py).

Every question is asked several times. temperature=0 turned out not to be
deterministic in practice: the same unchanged prompt answered one question
honestly on one run and with an invented duration on the next, so a single
pass can make a failing prompt look clean.

It also measures the grounding check against the rules. That check is what
flags a claim for the human reviewing an answer; the eval reports how many of
the answers the rules call fabricated it actually flagged, and how many clean
answers it flagged anyway.
"""

import asyncio
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass

from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.tailoring.draft_answer import (
    generate_draft_answer,
    leaves_it_to_the_candidate,
)
from app.services.tailoring.grounding import grounding_source, verify_grounding
from evals.checks import EVERY_ANSWER, FABRICATION, CheckResult, Fits, LeftForCandidate
from evals.datasets.draft_answers import CANDIDATE, CASES, JOB, Case


@dataclass
class Sample:
    case_id: str
    run: int
    answer: str
    results: list[CheckResult]
    # What the grounding check called unsupported — what a reviewer would see.
    flagged: list[str]

    @property
    def failures(self) -> list[CheckResult]:
        return [result for result in self.results if not result.passed]

    @property
    def fabricated(self) -> bool:
        return any(result.category == FABRICATION for result in self.failures)


def _checks_for(case: Case) -> list:
    checks = [*case.checks, *EVERY_ANSWER, LeftForCandidate(case.left_for_candidate)]
    if case.max_length is not None:
        checks.append(Fits(case.max_length))
    return checks


async def _sample(case: Case, run: int, job: JobModel, gate: asyncio.Semaphore) -> Sample:
    # Never persisted — the generator only reads attributes, so a transient
    # object is the candidate without a database anywhere near the eval.
    profile = Profile(**{**CANDIDATE, **case.candidate}, projects=[])
    async with gate:
        answer = await generate_draft_answer(profile, job, case.question, case.max_length)
        # Handed back to the candidate, the pipeline stores nothing and checks
        # nothing — mirrored here, so the grounding check's figures cover only
        # answers that would actually reach a reviewer.
        flagged = []
        if not leaves_it_to_the_candidate(answer):
            flagged = (await verify_grounding(answer, grounding_source(profile))).unverified_claims
    results = [check.evaluate(answer) for check in _checks_for(case)]
    return Sample(case.id, run, answer, results, flagged)


def _clip(text: str, width: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def report(samples: list[Sample], runs: int, cases: list[Case]) -> str:
    lines = [
        f"Draft answers — {len(cases)} questions × {runs} runs = {len(samples)} answers",
        "",
    ]

    applied: Counter[tuple[str, str]] = Counter()
    failed: Counter[tuple[str, str]] = Counter()
    for sample in samples:
        for result in sample.results:
            applied[(result.check, result.category)] += 1
            failed[(result.check, result.category)] += not result.passed

    lines.append("By rule                              failed")
    for key in sorted(applied, key=lambda k: (-failed[k], k)):
        check, category = key
        lines.append(f"  {check:<20} {category:<12}  {failed[key]:>3} / {applied[key]}")

    by_case: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        by_case[sample.case_id].append(sample)

    failing = [case for case in cases if any(s.failures for s in by_case[case.id])]
    lines += ["", f"Questions with a failure: {len(failing)} of {len(cases)}"]
    for case in failing:
        bad = [s for s in by_case[case.id] if s.failures]
        first = bad[0].failures[0]
        lines.append(
            f"  {case.id:<30} {len(bad)}/{runs}  {first.check}: {_clip(first.evidence, 60)}"
        )
        lines.append(f"      e.g. {_clip(bad[0].answer)}")

    fabricated = [s for s in samples if s.fabricated]
    clean = [s for s in samples if not s.failures]
    caught = sum(1 for s in fabricated if s.flagged)
    false_alarms = [s for s in clean if s.flagged]
    lines += [
        "",
        "The grounding check on the same answers",
        f"  flagged {caught} of {len(fabricated)} answers the rules call fabricated",
        f"  flagged {len(false_alarms)} of {len(clean)} answers that passed every rule",
    ]
    for sample in false_alarms[:5]:
        lines.append(f"      {sample.case_id}: {_clip('; '.join(sample.flagged), 70)}")

    total_failed = sum(1 for s in samples if s.failures)
    lines += [
        "",
        (
            f"{len(samples) - total_failed} of {len(samples)} answers passed every rule; "
            f"{len(fabricated)} contained a fabrication."
        ),
    ]
    return "\n".join(lines)


async def collect(
    runs: int, concurrency: int, only: list[str] | None
) -> tuple[list[Sample], list[Case]]:
    job = JobModel(**JOB)
    cases = [case for case in CASES if not only or case.id in only]
    if only and len(cases) != len(set(only)):
        known = {case.id for case in CASES}
        raise SystemExit(f"Unknown case id(s): {sorted(set(only) - known)}")

    gate = asyncio.Semaphore(concurrency)
    samples = await asyncio.gather(
        *(_sample(case, i, job, gate) for case in cases for i in range(runs))
    )
    return list(samples), cases


def rescore(path: str) -> tuple[list[Sample], list[Case], int]:
    """Judge answers saved by an earlier --out again, under the current rules.

    No model call — the answers and the grounding check's flags are read back
    as they were. This is how a before/after stays honest when the rules
    themselves improve: the first version of the expected-CTC case missed an
    invented "10 LPA", and only re-judging the saved baseline under the fixed
    rule shows what that baseline really contained.
    """
    with open(path, encoding="utf-8") as handle:
        rows = json.load(handle)
    by_id = {case.id: case for case in CASES}
    samples = [
        Sample(
            row["case_id"],
            row["run"],
            row["answer"],
            [check.evaluate(row["answer"]) for check in _checks_for(by_id[row["case_id"]])],
            row["flagged"],
        )
        for row in rows
    ]
    seen = {sample.case_id for sample in samples}
    runs = max(sample.run for sample in samples) + 1
    return samples, [case for case in CASES if case.id in seen], runs


def run(
    runs: int = 5,
    concurrency: int = 6,
    only: list[str] | None = None,
    out: str | None = None,
    rescore_path: str | None = None,
) -> int:
    if rescore_path:
        samples, cases, runs = rescore(rescore_path)
    else:
        samples, cases = asyncio.run(collect(runs, concurrency, only))

    print(report(samples, runs, cases))
    if out:
        with open(out, "w", encoding="utf-8") as handle:
            json.dump([asdict(sample) for sample in samples], handle, indent=2)
        print(f"\nEvery answer written to {out}")

    return 1 if any(sample.failures for sample in samples) else 0
