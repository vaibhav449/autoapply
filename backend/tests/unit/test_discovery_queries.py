import pytest

from app.models.profile import TargetLevel
from app.services.discovery.queries import (
    EXCLUDE_ABOVE,
    build_adzuna_queries,
    queries_for_level,
)


@pytest.mark.parametrize(
    ("level", "expected_term"),
    [
        (TargetLevel.INTERN, "intern"),
        (TargetLevel.NEW_GRAD, "fresher"),
        (TargetLevel.JUNIOR, "junior"),
        (TargetLevel.SENIOR, "senior"),
    ],
)
def test_each_level_searches_for_its_own_vocabulary(level, expected_term) -> None:
    whats = [q.what for q in queries_for_level(level)]

    assert any(expected_term in what for what in whats)


def test_mid_level_searches_the_bare_role() -> None:
    whats = [q.what for q in queries_for_level(TargetLevel.MID)]

    assert "backend engineer" in whats
    # no stray whitespace from the empty level term
    assert all(what == what.strip() for what in whats)


def test_queries_stay_short_because_adzuna_ands_every_word() -> None:
    """Measured: "graduate entry level software developer" returned 0 results,
    while three-word queries returned 6 and 20.
    """
    for level in TargetLevel:
        for query in queries_for_level(level):
            assert len(query.what.split()) <= 4, query.what


def test_junior_searches_exclude_senior_titles() -> None:
    for query in queries_for_level(TargetLevel.INTERN):
        assert "senior" in query.what_exclude
        assert "principal" in query.what_exclude


def test_senior_searches_exclude_nothing() -> None:
    assert EXCLUDE_ABOVE[TargetLevel.SENIOR] == ""
    assert all(q.what_exclude == "" for q in queries_for_level(TargetLevel.SENIOR))


def test_budget_is_respected() -> None:
    queries = build_adzuna_queries({TargetLevel.INTERN, TargetLevel.SENIOR}, budget=7)

    assert len(queries) == 7


def test_a_tight_budget_still_covers_every_level() -> None:
    """Interleaving matters: a naive concatenation would spend the whole budget on
    the first level and never search for the others at all.
    """
    levels = {TargetLevel.INTERN, TargetLevel.SENIOR}

    queries = build_adzuna_queries(levels, budget=4)

    assert any("intern" in q.what for q in queries)
    assert any("senior" in q.what for q in queries)


def test_no_profiles_means_no_queries() -> None:
    assert build_adzuna_queries(set()) == []


def test_queries_are_unique() -> None:
    queries = build_adzuna_queries(set(TargetLevel), budget=200)
    keys = [(q.what, q.where) for q in queries]

    assert len(keys) == len(set(keys))
