import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ats_board import AtsBoard
from app.schemas.job import Job
from app.services.discovery.ashby import discover_ashby_jobs
from app.services.discovery.greenhouse import discover_greenhouse_jobs
from app.services.discovery.lever import discover_lever_jobs
from app.services.discovery.smartrecruiters import discover_smartrecruiters_jobs

logger = logging.getLogger(__name__)

BoardAdapter = Callable[[str, AsyncSession], Awaitable[list[Job]]]

BOARD_ADAPTERS: dict[str, BoardAdapter] = {
    "greenhouse": discover_greenhouse_jobs,
    "lever": discover_lever_jobs,
    "ashby": discover_ashby_jobs,
    "smartrecruiters": discover_smartrecruiters_jobs,
}


async def poll_active_boards(db: AsyncSession) -> dict[str, int]:
    """Poll every active board, one at a time.

    Each board is committed on its own: a company whose board 404s or times out
    must not discard the jobs already fetched from the boards before it.
    """
    boards = list(
        (await db.execute(select(AtsBoard).where(AtsBoard.active))).scalars().all()
    )
    stats = {"boards": len(boards), "polled": 0, "jobs": 0, "deactivated": 0, "failed": 0}

    for board in boards:
        adapter = BOARD_ADAPTERS.get(board.source)
        if adapter is None:
            logger.warning("no adapter for ATS source %s", board.source)
            continue

        try:
            jobs = await adapter(board.slug, db)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                # The board is gone, not merely unreachable. Self-pruning: stop
                # polling it, and stop treating its absence as jobs closing.
                board.active = False
                stats["deactivated"] += 1
                logger.info("deactivated missing board %s/%s", board.source, board.slug)
            else:
                stats["failed"] += 1
                logger.warning("board %s/%s failed: %s", board.source, board.slug, exc)
            await db.commit()
            continue
        except (httpx.HTTPError, ValueError) as exc:
            stats["failed"] += 1
            logger.warning("board %s/%s failed: %s", board.source, board.slug, exc)
            continue

        board.last_polled_at = datetime.now(UTC)
        stats["polled"] += 1
        stats["jobs"] += len(jobs)
        await db.commit()

    return stats
