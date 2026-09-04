import re

GREENHOUSE_URL_PATTERN = re.compile(r"(?:boards|job-boards)\.greenhouse\.io/([\w-]+)")
LEVER_URL_PATTERN = re.compile(r"jobs\.lever\.co/([\w-]+)")


def resolve_known_ats(url: str) -> tuple[str, str] | None:
    """If `url` is hosted directly on a known ATS's own domain, return (source, company_slug)."""
    if match := GREENHOUSE_URL_PATTERN.search(url):
        return ("greenhouse", match.group(1))
    if match := LEVER_URL_PATTERN.search(url):
        return ("lever", match.group(1))
    return None