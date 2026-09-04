from app.services.discovery.url_resolver import resolve_known_ats


def test_resolves_greenhouse_boards_domain() -> None:
    assert resolve_known_ats("https://boards.greenhouse.io/stripe") == ("greenhouse", "stripe")


def test_resolves_greenhouse_job_boards_domain() -> None:
    assert resolve_known_ats("https://job-boards.greenhouse.io/acme") == ("greenhouse", "acme")


def test_resolves_lever_domain() -> None:
    assert resolve_known_ats("https://jobs.lever.co/palantir") == ("lever", "palantir")


def test_returns_none_for_unknown_domain() -> None:
    assert resolve_known_ats("https://careers.acme.com/jobs") is None