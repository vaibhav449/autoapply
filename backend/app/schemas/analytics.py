from pydantic import BaseModel


class VariantPerformance(BaseModel):
    """How one resume variant has actually done.

    Counts, not just a rate: at these sample sizes "50%" is one application
    either way, and a bare percentage invites reading a pattern into noise.
    """

    variant_id: int
    role_label: str
    submitted: int
    responded: int
    interviews: int


class AnalyticsSummary(BaseModel):
    # MVP.md's funnel: applied -> response -> interview. Each stage counts what
    # was actually recorded, never inferred from a later one — an offer with no
    # interview logged means the interview was not recorded, and quietly adding
    # it would invent history.
    started: int
    submitted: int
    responded: int
    interviewed: int
    offers: int

    by_state: dict[str, int]
    by_outcome: dict[str, int]
    variants: list[VariantPerformance]
