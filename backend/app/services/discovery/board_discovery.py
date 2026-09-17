import asyncio
import logging
import re

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ats_board import AtsBoard
from app.models.job import Job as JobModel

logger = logging.getLogger(__name__)

CONCURRENCY = 6
TIMEOUT = 12.0

LEGAL_NOISE = re.compile(
    r"\b(pvt|private|ltd|limited|inc|llc|llp|corp|corporation|gmbh|"
    r"technologies|technology|solutions|systems|labs|global|group|"
    r"services|consulting|software)\b"
)

ALL_SOURCES = ("greenhouse", "lever", "ashby", "smartrecruiters")

# How much board content to keep for corroborating a fuzzy slug. Greenhouse and
# SmartRecruiters state the owner's name outright; Lever and Ashby don't, so for
# those we check whether the company's name actually appears in the board's own
# postings. Without some check, a fuzzy guess silently imports a stranger's jobs —
# "New Era India" matched a board owned by "Sonja Inc.", and "Cornerstone OnDemand"
# matched a child development centre.
CONTENT_SAMPLE_JOBS = 3
CONTENT_SAMPLE_CHARS = 3000


def strict_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def fuzzy_slugs(name: str) -> list[str]:
    """Slug guesses beyond the literal one. Deliberately excludes the bare first
    word — that is what produced "New Era India" -> "new".
    """
    base = name.lower().strip()
    candidates = [
        re.sub(r"[^a-z0-9]+", "-", base).strip("-"),
        re.sub(r"[^a-z0-9]", "", LEGAL_NOISE.sub(" ", base)),
    ]
    strict = strict_slug(name)
    out: list[str] = []
    for candidate in candidates:
        if candidate and len(candidate) >= 4 and candidate != strict and candidate not in out:
            out.append(candidate)
    return out


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", LEGAL_NOISE.sub(" ", name.lower()))


def names_match(wanted: str, declared: str | None) -> bool:
    left, right = _normalize_name(wanted), _normalize_name(declared or "")
    if not left or not right:
        return False
    return left in right or right in left


class BoardProbe:
    """What a board tells us about itself, for corroborating a slug guess."""

    def __init__(self, count: int, declared_name: str | None = None, content: str = "") -> None:
        self.count = count
        self.declared_name = declared_name
        self.content = content

    def corroborates(self, company: str) -> bool:
        return names_match(company, self.declared_name) or names_match(company, self.content)


def _sample(jobs: list[dict], title_key: str, body_key: str) -> str:
    parts = []
    for job in jobs[:CONTENT_SAMPLE_JOBS]:
        parts.append(str(job.get(title_key) or ""))
        parts.append(str(job.get(body_key) or "")[:CONTENT_SAMPLE_CHARS])
    return " ".join(parts)


async def probe_board(client: httpx.AsyncClient, source: str, slug: str) -> BoardProbe | None:
    """Returns what the board says about itself, or None if it doesn't exist."""
    try:
        if source == "greenhouse":
            meta = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}")
            if meta.status_code != 200:
                return None
            jobs = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
            listings = jobs.json().get("jobs", []) if jobs.status_code == 200 else []
            return BoardProbe(len(listings), meta.json().get("name"), _sample(listings, "title", "content"))

        if source == "lever":
            r = await client.get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
            if r.status_code != 200:
                return None
            data = r.json()
            listings = data if isinstance(data, list) else []
            return BoardProbe(len(listings), None, _sample(listings, "text", "descriptionPlain"))

        if source == "ashby":
            r = await client.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
            if r.status_code != 200:
                return None
            listings = r.json().get("jobs", [])
            return BoardProbe(len(listings), None, _sample(listings, "title", "descriptionPlain"))

        if source == "smartrecruiters":
            # No 404 here: an unknown company answers 200 with totalFound 0, so only
            # a non-empty result proves the board exists.
            r = await client.get(
                f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                params={"limit": 1},
            )
            if r.status_code != 200:
                return None
            payload = r.json()
            if payload.get("totalFound", 0) <= 0:
                return None
            content = payload.get("content") or []
            declared = (content[0].get("company") or {}).get("name") if content else None
            return BoardProbe(payload["totalFound"], declared)
    except httpx.HTTPError:
        return None
    return None


async def find_board_for_company(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, company: str
) -> AtsBoard | None:
    """Strict slug against every ATS first; then fuzzy guesses, but only against
    sources that let us confirm who owns the board.
    """
    slug = strict_slug(company)
    if len(slug) >= 3:
        for source in ALL_SOURCES:
            async with sem:
                probe = await probe_board(client, source, slug)
            if probe:
                # An exact slug match needs no corroboration — the company's own
                # name IS the slug.
                return AtsBoard(
                    source=source,
                    slug=slug,
                    company_name=company,
                    verified_name=probe.declared_name,
                    discovered_via="adzuna",
                )

    for candidate in fuzzy_slugs(company):
        for source in ALL_SOURCES:
            async with sem:
                probe = await probe_board(client, source, candidate)
            if not probe:
                continue
            if not probe.corroborates(company):
                logger.info(
                    "rejected fuzzy match %s/%s for %r (board says %r)",
                    source,
                    candidate,
                    company,
                    probe.declared_name,
                )
                continue
            return AtsBoard(
                source=source,
                slug=candidate,
                company_name=company,
                verified_name=probe.declared_name,
                discovered_via="adzuna",
            )
    return None


async def discover_boards_from_aggregators(db: AsyncSession, limit: int = 250) -> dict[str, int]:
    """Look for readable ATS boards belonging to companies that only reached us
    through an aggregator, where descriptions are truncated and liveness is
    unverifiable. Finding the board upgrades every future job from that company.
    """
    aggregator_companies = {
        name
        for (name,) in (
            await db.execute(
                select(JobModel.company).where(JobModel.source.in_(("adzuna", "jooble")))
            )
        ).all()
        if name and name.lower() != "unknown company"
    }
    already = {
        name for (name,) in (await db.execute(select(AtsBoard.company_name))).all()
    }
    todo = sorted(aggregator_companies - already)[:limit]

    stats = {"considered": len(todo), "found": 0, "jobs_behind_boards": 0}
    if not todo:
        return stats

    sem = asyncio.Semaphore(CONCURRENCY)
    headers = {"User-Agent": "AutoApply/0.1 (job board discovery)"}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as client:
        results = await asyncio.gather(
            *(find_board_for_company(client, sem, company) for company in todo)
        )

    existing_keys = {
        (source, slug)
        for source, slug in (await db.execute(select(AtsBoard.source, AtsBoard.slug))).all()
    }
    for board in results:
        if board is None or (board.source, board.slug) in existing_keys:
            continue
        existing_keys.add((board.source, board.slug))
        db.add(board)
        stats["found"] += 1

    await db.commit()
    return stats
