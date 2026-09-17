from dataclasses import dataclass

from app.models.profile import TargetLevel

# Adzuna ANDs every word in `what`, so long phrases return nothing — measured:
# "graduate entry level software developer" gave 0 results while "fresher software
# engineer" gave 6 and "software engineer intern" gave 20. Level terms are
# therefore single words bolted onto a short role, and the real filtering happens
# in `what_exclude`, which cut senior-sounding titles from 12/20 to 0/20.
LEVEL_TERMS: dict[TargetLevel, tuple[str, ...]] = {
    TargetLevel.INTERN: ("intern", "internship"),
    TargetLevel.NEW_GRAD: ("fresher", "graduate"),
    TargetLevel.JUNIOR: ("junior", "associate"),
    TargetLevel.MID: ("",),
    TargetLevel.SENIOR: ("senior",),
}

# Titles that sit above the target level and should never enter the pool.
EXCLUDE_ABOVE: dict[TargetLevel, str] = {
    TargetLevel.INTERN: "senior lead principal staff architect manager director head",
    TargetLevel.NEW_GRAD: "senior lead principal staff architect manager director head",
    TargetLevel.JUNIOR: "senior principal staff architect director head",
    TargetLevel.MID: "principal staff director head",
    TargetLevel.SENIOR: "",
}

ROLES: tuple[str, ...] = (
    "backend engineer",
    "software engineer",
    "full stack developer",
    "data engineer",
    "python developer",
)

LOCATIONS: tuple[str, ...] = ("Bangalore", "India", "remote")


@dataclass(frozen=True)
class AdzunaQuery:
    what: str
    where: str
    what_exclude: str


def queries_for_level(level: TargetLevel) -> list[AdzunaQuery]:
    exclude = EXCLUDE_ABOVE[level]
    seen: set[tuple[str, str]] = set()
    queries: list[AdzunaQuery] = []

    # Role varies fastest so a truncated budget still spans several roles rather
    # than exhausting every location for one of them.
    for term in LEVEL_TERMS[level]:
        for location in LOCATIONS:
            for role in ROLES:
                what = f"{role} {term}".strip()
                if (what, location) in seen:
                    continue
                seen.add((what, location))
                queries.append(AdzunaQuery(what=what, where=location, what_exclude=exclude))
    return queries


def build_adzuna_queries(
    levels: set[TargetLevel], budget: int = 18
) -> list[AdzunaQuery]:
    """Interleave each level's queries so a tight budget covers every level the
    users actually want, rather than spending itself entirely on the first one.

    Budget exists because Adzuna's free tier allows roughly 33 calls a day and one
    call is one query.
    """
    if not levels:
        return []

    per_level = [queries_for_level(level) for level in sorted(levels, key=lambda lvl: lvl.value)]
    interleaved: list[AdzunaQuery] = []
    for index in range(max(len(queries) for queries in per_level)):
        for queries in per_level:
            if index < len(queries):
                interleaved.append(queries[index])
    return interleaved[:budget]
