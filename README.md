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
uvicorn app.main:app --reload

cd ../frontend
npm install
npm run dev
```

## Status

Early scaffold — see MVP.md §8 for the current phase.
