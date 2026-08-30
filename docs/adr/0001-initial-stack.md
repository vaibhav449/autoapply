# 1. Initial stack and monorepo layout

## Status
Accepted

## Context
See [MVP.md](../../MVP.md) for full scope and rationale. Need a backend capable of async browser automation (Playwright) and background job processing (Celery), plus a dashboard frontend, without introducing tooling unfamiliar to the builder.

## Decision
- Backend: FastAPI (async) + SQLAlchemy async + Alembic + Celery/Redis + Playwright
- Frontend: Next.js App Router
- Single monorepo, two deployable apps (`backend/`, `frontend/`), shared CI/docs at root
- Postgres as the system of record; the application state machine (MVP.md §4) lives in the DB, not in Celery task state

## Consequences
- Async SQLAlchemy requires the Alembic async template for migrations (sync engine_from_config would fail against an asyncpg URL)
- Single-user in v1 — schema should avoid hard-coding single-tenant assumptions where cheap to avoid (see MVP.md §3 deferred scope)
