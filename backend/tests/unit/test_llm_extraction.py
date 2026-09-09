from app.services.discovery.llm_extraction import extract_links

PAGE_HTML = """
<html><body>
<nav><a href="/about">About</a></nav>
<a href="/jobs/123">Senior Backend Engineer - Remote</a>
<a href="/jobs/456">Product Designer - NYC</a>
<a href="https://twitter.com/acme"><img src="icon.png"></a>
</body></html>
"""


def test_extracts_visible_links_with_absolute_urls() -> None:
    links = extract_links(PAGE_HTML, "https://acme.test/careers")

    texts = {link["text"] for link in links}
    assert "Senior Backend Engineer - Remote" in texts
    assert "Product Designer - NYC" in texts

    job_link = next(link for link in links if "Backend" in link["text"])
    assert job_link["url"] == "https://acme.test/jobs/123"


def test_skips_links_with_no_visible_text() -> None:
    links = extract_links(PAGE_HTML, "https://acme.test/careers")

    # the twitter icon link has no visible text (just an <img>) — must be excluded
    assert not any("twitter.com" in link["url"] for link in links)
