"""Run an eval suite against its labeled dataset in evals/datasets/.

    cd backend
    python -m evals.run_eval draft_answers --runs 5
    python -m evals.run_eval draft_answers --only python-years --runs 10

Exits non-zero when any answer breaks a rule, so it can gate a prompt change:
run it before and after, and the difference is what the change did.
"""

import argparse
import sys

from evals import draft_answers

SUITES = {"draft_answers": draft_answers.run}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("suite", choices=sorted(SUITES))
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="times each question is asked (default 5) — temperature 0 is not deterministic",
    )
    parser.add_argument("--concurrency", type=int, default=6, help="requests in flight at once")
    parser.add_argument("--only", action="append", help="run just this case id (repeatable)")
    parser.add_argument("--out", help="write every answer and verdict to this JSON file")
    parser.add_argument(
        "--rescore",
        metavar="FILE",
        help="re-judge answers saved by an earlier --out under the current rules (no model call)",
    )
    args = parser.parse_args(argv)

    # The report uses dashes and ellipses; a Windows console defaults to cp1252.
    sys.stdout.reconfigure(encoding="utf-8")
    return SUITES[args.suite](
        runs=args.runs,
        concurrency=args.concurrency,
        only=args.only,
        out=args.out,
        rescore_path=args.rescore,
    )


if __name__ == "__main__":
    sys.exit(main())
