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

## Status

Early scaffold — see MVP.md §8 for the current phase.
