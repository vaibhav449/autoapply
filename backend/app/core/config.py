from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # Resolved from this file's own location, not the process's cwd, so it finds the
    # same repo-root .env regardless of which directory a command is run from (matches
    # what docker-compose.yml's `env_file: .env` already expects).
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"
    secret_key: str = "change-me"

    database_url: str = "postgresql+asyncpg://autoapply:autoapply@localhost:5432/autoapply"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    anthropic_api_key: str = ""
    openai_api_key: str = ""

    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    jooble_api_key: str = ""


settings = Settings()
