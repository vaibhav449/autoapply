import pytest

from app.services.discovery.board_discovery import (
    BoardProbe,
    fuzzy_slugs,
    names_match,
    strict_slug,
)


@pytest.mark.parametrize(
    ("company", "expected"),
    [
        ("Stripe", "stripe"),
        ("Arista Networks", "aristanetworks"),
        ("Spector.ai", "spectorai"),
        ("People Tech Group Inc", "peopletechgroupinc"),
    ],
)
def test_strict_slug(company, expected) -> None:
    assert strict_slug(company) == expected


def test_fuzzy_slugs_never_emit_a_bare_first_word() -> None:
    """The variant that produced "New Era India" -> "new", which matched a
    Greenhouse board belonging to Sonja Inc.
    """
    assert "new" not in fuzzy_slugs("New Era India")
    assert "cornerstone" not in fuzzy_slugs("Cornerstone OnDemand")


def test_fuzzy_slugs_strip_legal_noise_and_hyphenate() -> None:
    assert "tekion" in fuzzy_slugs("Tekion Corp")
    assert "metronsecurity" in fuzzy_slugs("Metron Security Private Limited")
    assert "spector-ai" in fuzzy_slugs("Spector.ai")


def test_fuzzy_slugs_exclude_the_strict_slug_itself() -> None:
    assert strict_slug("Toptal") not in fuzzy_slugs("Toptal")


@pytest.mark.parametrize(
    ("company", "declared", "expected"),
    [
        ("Metron Security Private Limited", "Metron", True),
        ("Tekion Corp", "Tekion", True),
        ("slice", "Slice", True),
        ("ValueLabs", "Value Labs", True),
        # the two real false positives this check exists to stop
        ("New Era India", "Sonja Inc.", False),
        ("Cornerstone OnDemand", "Cornerstone Child Development Center", False),
        ("Anything", None, False),
        ("Anything", "", False),
    ],
)
def test_names_match(company, declared, expected) -> None:
    assert names_match(company, declared) is expected


def test_a_board_can_corroborate_itself_through_its_job_content() -> None:
    """Lever and Ashby never state the owner's name, so a fuzzy slug is accepted
    there only when the company shows up in the board's own postings.
    """
    probe = BoardProbe(
        count=114,
        declared_name=None,
        content="Manager AI ABOUT TEKION: Positively disrupting an industry...",
    )

    assert probe.corroborates("Tekion Corp") is True


def test_unrelated_job_content_does_not_corroborate() -> None:
    probe = BoardProbe(count=3, declared_name=None, content="Barista wanted at Sonja Inc.")

    assert probe.corroborates("New Era India") is False


def test_a_declared_name_alone_is_enough() -> None:
    assert BoardProbe(5, declared_name="Capco", content="").corroborates("Capco") is True
