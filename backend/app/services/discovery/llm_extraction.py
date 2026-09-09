from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from pydantic import BaseModel

from app.schemas.job import Job
from app.services.llm_gateway import openai_client


class ExtractedJob(BaseModel):
    title: str
    url: str
    location: str | None = None


class ExtractedJobsResponse(BaseModel):
    jobs: list[ExtractedJob]


async def render_page(url: str) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url, wait_until="load", timeout=30_000)
        html = await page.content()
        await browser.close()
        return html


def extract_links(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if text:
            links.append({"text": text, "url": urljoin(base_url, a["href"])})
    return links


async def call_llm_for_jobs(links: list[dict]) -> ExtractedJobsResponse:
    links_text = "\n".join(f"- {link['text']} -> {link['url']}" for link in links)

    completion = await openai_client.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are given every link found on a company's careers page, as "
                    "'text -> url' lines. Identify which ones are actual job postings "
                    "(not navigation, footer, social, or generic 'apply now' links) and "
                    "extract each one's title, url, and location if it's mentioned in "
                    "the link text. If nothing looks like a job posting, return an "
                    "empty list."
                ),
            },
            {"role": "user", "content": links_text},
        ],
        response_format=ExtractedJobsResponse,
    )

    message = completion.choices[0].message
    if message.parsed is None:
        raise ValueError(f"LLM did not return valid structured output: {message.refusal}")
    return message.parsed


async def fetch_llm_extracted_jobs(url: str) -> list[Job]:
    html = await render_page(url)
    links = extract_links(html, url)
    extracted = await call_llm_for_jobs(links)

    company = httpx.URL(url).host

    return [
        Job(
            external_id=job.url,
            source="llm-extraction",
            title=job.title,
            company=company,
            location=job.location,
            url=job.url,
        )
        for job in extracted.jobs
    ]
