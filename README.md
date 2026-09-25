# AutoApply

Automated job application pipeline: discovers jobs matching your skills, scores and prioritizes them, tailors a resume + draft answers per posting, and queues each one for one-click human review-and-submit. CAPTCHA-blocked applications are routed to a pending list instead of being silently dropped.

See [MVP.md](./MVP.md) for full scope, architecture, and the phased build roadmap.

## Project layout

```
backend/    FastAPI + Celery + Playwright (Python, async)
frontend/   Next.js (App Router) dashboard
docs/adr/   Architecture decision records
```

## Local development

Prerequisites: Docker, Python 3.13+, Node 22+.

```bash
cp .env.example .env
docker compose up -d postgres redis

cd backend
pip install -e ".[dev]"
playwright install chromium
uvicorn app.main:app

cd ../frontend
npm install
npm run dev
```

**Run the backend without `--reload`.** On Windows that flag switches uvicorn to
a `SelectorEventLoop`, which cannot spawn subprocesses, so Playwright fails to
launch Chromium and every form fill dies with `NotImplementedError`. Nothing
else in the app notices, which makes it look like a bug in the automation
rather than in how the server was started. Restart the process by hand after
backend edits, or keep `--reload` only while working on code that never fills
a form.

`playwright install chromium` is separate from `pip install`: pip brings the
Python package, not the browser binary the form filler drives.

## Evals

`pytest` covers everything deterministic and never calls a model. What an LLM
actually writes is measured separately, against labeled datasets in
`backend/evals/datasets/`:

```bash
cd backend
python -m evals.run_eval draft_answers --runs 5 --out before.json
# ...change a prompt...
python -m evals.run_eval draft_answers --runs 5 --out after.json
```

`python -m evals.run_eval dropdowns` does the same for the option picker, which
cannot invent prose but can still pick a false option — it once answered a US
sponsorship question "No" for a candidate authorized only in India.

Both call the real model, so they need `OPENAI_API_KEY` and cost a few cents a
run — they are run by hand around prompt changes, not in CI. Each question is asked
several times because temperature 0 is not deterministic in practice: a failure
that shows up on half the runs looks clean on a single pass. `--rescore FILE`
re-judges saved answers under the current rules without calling the model, which
keeps a before/after honest when the rules themselves improve.

## Status

Early scaffold — see MVP.md §8 for the current phase.
