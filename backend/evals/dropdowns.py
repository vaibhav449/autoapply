"""The dropdown eval: how often does the option picker choose something false?

    cd backend
    python -m evals.run_eval dropdowns --runs 5

The text suite never covered this path, and it had a failure of its own: an
authorization for India answered a question about the United States with "No,
I will not need sponsorship" on every run. A dropdown pick cannot be invented
prose — it is checked against the form's own options — but it can still be a
false statement, and that is what this measures.

Like the text suite it calls the real model (a few cents a run, needs
OPENAI_API_KEY) and asks every question several times, because temperature 0
is not deterministic in practice.
"""

import asyncio
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass

from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.tailoring.draft_answer import choose_draft_option
from evals.datasets.draft_answers import JOB
from evals.datasets.dropdowns import CASES, DropdownCase

OK = "ok"
# The pick states something untrue about the candidate.
FALSE = "false"
# Neither acceptable nor false — a pick the question's rules do not allow, such
# as a guess the candidate's details do not support in either direction.
OFF = "off"


def judge(case: DropdownCase, pick: str | None) -> str:
    if pick in case.acceptable:
        return OK
    if pick in case.false_picks:
        return FALSE
    return OFF


@dataclass
class Sample:
    case_id: str
    run: int
    pick: str | None
    verdict: str


async def _sample(case: DropdownCase, run: int, job: JobModel, gate: asyncio.Semaphore) -> Sample:
    # Never persisted, same as the text suite.
    profile = Profile(**case.profile_fields(), projects=[])
    async with gate:
        pick = await choose_draft_option(profile, job, case.question, list(case.options))
    return Sample(case.id, run, pick, judge(case, pick))


def report(samples: list[Sample], runs: int, cases: list[DropdownCase]) -> str:
    verdicts = Counter(sample.verdict for sample in samples)
    by_case: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        by_case[sample.case_id].append(sample)

    lines = [
        f"Dropdowns — {len(cases)} questions × {runs} runs = {len(samples)} picks",
        "",
        f"  false statements   {verdicts[FALSE]:>3} / {len(samples)}",
        f"  off-contract picks {verdicts[OFF]:>3} / {len(samples)}",
        "",
    ]
    for case in cases:
        picks = Counter("—leave it—" if s.pick is None else s.pick for s in by_case[case.id])
        worst = FALSE if any(s.verdict == FALSE for s in by_case[case.id]) else (
            OFF if any(s.verdict == OFF for s in by_case[case.id]) else OK
        )
        label = {OK: "ok   ", FALSE: "FALSE", OFF: "OFF  "}[worst]
        lines.append(f"  {label} {case.id:<32} {dict(picks)}")

    failing = sum(1 for case in cases if any(s.verdict != OK for s in by_case[case.id]))
    lines += ["", f"Questions with a failure: {failing} of {len(cases)}"]
    return "\n".join(lines)


async def collect(
    runs: int, concurrency: int, only: list[str] | None
) -> tuple[list[Sample], list[DropdownCase]]:
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


def rescore(path: str) -> tuple[list[Sample], list[DropdownCase], int]:
    """Re-judge picks saved by an earlier --out under the current labels."""
    with open(path, encoding="utf-8") as handle:
        rows = json.load(handle)
    by_id = {case.id: case for case in CASES}
    samples = [
        Sample(row["case_id"], row["run"], row["pick"], judge(by_id[row["case_id"]], row["pick"]))
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
        print(f"\nEvery pick written to {out}")

    return 1 if any(sample.verdict != OK for sample in samples) else 0
