from functools import lru_cache

from openai import AsyncOpenAI

from app.core.config import settings


@lru_cache
def _build_client() -> AsyncOpenAI:
    # Falls back to a placeholder key instead of settings.openai_api_key's "" default,
    # since an empty string (unlike None) makes AsyncOpenAI raise on construction rather
    # than deferring to the OPENAI_API_KEY env var — breaking every test that merely
    # imports this module (transitively, via jobs/cover_letter/resume_variant/etc.) in
    # any environment without a real key configured, e.g. CI.
    return AsyncOpenAI(api_key=settings.openai_api_key or "not-configured")


class _LazyOpenAIClient:
    """Defers AsyncOpenAI construction to first attribute access, so importing this
    module never requires a real API key — only actually calling the client does."""

    def __getattr__(self, name: str):
        return getattr(_build_client(), name)


openai_client = _LazyOpenAIClient()
