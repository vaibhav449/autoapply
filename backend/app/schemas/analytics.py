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


class SkippedField(BaseModel):
    """One field the filler kept leaving for a human, and how often.

    This is the tool's own backlog, measured rather than guessed: a field near
    the top is either a control no adapter handles yet or a question the
    grounded generator is right to refuse, and the two are worth telling apart
    before writing any more adapter code.
    """

    field: str
    # Runs it was skipped in, and how many distinct applications those were —
    # a form filled three times over would otherwise look like three problems.
    runs: int
    applications: int


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

    # Recorded runs of the form-filler, and what they could not answer. Note
    # this deliberately carries no time-saved or cost figure: the filler's own
    # duration is measured, but the manual baseline it would be subtracted from
    # is not, and inventing one would make the headline number fiction.
    fill_runs: int
    skipped_fields: list[SkippedField]
