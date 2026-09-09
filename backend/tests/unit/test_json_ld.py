import httpx
import respx

from app.services.discovery.json_ld import fetch_json_ld_jobs

PAGE_WITH_JOB_POSTING = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "JobPosting",
  "title": "Staff Engineer",
  "hiringOrganization": {"@type": "Organization", "name": "Acme Inc"},
  "jobLocation": {
    "@type": "Place",
    "address": {"@type": "PostalAddress", "addressLocality": "Austin, TX"}
  }
}
</script>
</head><body></body></html>
"""

PAGE_WITH_NO_ORG_OR_LOCATION = """
<html><head>
<script type="application/ld+json">
{"@context": "https://schema.org/", "@type": "JobPosting", "title": "Contractor Role"}
</script>
</head><body></body></html>
"""

PAGE_WITH_NO_JOB_POSTING = "<html><head></head><body>Nothing here</body></html>"


@respx.mock
async def test_extracts_job_posting_with_org_and_location() -> None:
    respx.get("https://acme.test/careers/staff-engineer").mock(
        return_value=httpx.Response(200, text=PAGE_WITH_JOB_POSTING)
    )

    jobs = await fetch_json_ld_jobs("https://acme.test/careers/staff-engineer")

    assert len(jobs) == 1
    assert jobs[0].source == "json-ld"
    assert jobs[0].title == "Staff Engineer"
    assert jobs[0].company == "Acme Inc"
    assert jobs[0].location == "Austin, TX"
    assert jobs[0].external_id == "https://acme.test/careers/staff-engineer"


@respx.mock
async def test_falls_back_to_domain_when_org_missing() -> None:
    respx.get("https://acme.test/careers/contractor").mock(
        return_value=httpx.Response(200, text=PAGE_WITH_NO_ORG_OR_LOCATION)
    )

    jobs = await fetch_json_ld_jobs("https://acme.test/careers/contractor")

    assert len(jobs) == 1
    assert jobs[0].company == "acme.test"
    assert jobs[0].location is None


@respx.mock
async def test_returns_empty_list_when_no_job_posting_present() -> None:
    respx.get("https://acme.test/about").mock(
        return_value=httpx.Response(200, text=PAGE_WITH_NO_JOB_POSTING)
    )

    jobs = await fetch_json_ld_jobs("https://acme.test/about")

    assert jobs == []
