import asyncio

from app.services.discovery.greenhouse import fetch_greenhouse_jobs


async def main() -> None:
    jobs = await fetch_greenhouse_jobs("stripe")
    for job in jobs[:5]:
        print(job.title, "-", job.location)
    print(f"\n{len(jobs)} jobs found")


if __name__ == "__main__":
    asyncio.run(main())
