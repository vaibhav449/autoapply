from fastapi import FastAPI

from app.api.v1.routers import analytics, applications, jobs, profiles, resumes
from app.core.logging import setup_logging

setup_logging()

app = FastAPI(title="AutoApply API", version="0.1.0")

app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(profiles.router, prefix="/api/v1/profiles", tags=["profiles"])
app.include_router(applications.router, prefix="/api/v1/applications", tags=["applications"])
app.include_router(resumes.router, prefix="/api/v1/resumes", tags=["resumes"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
