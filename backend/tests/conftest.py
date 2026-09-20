from unittest.mock import patch

import pytest


def _forbidden(what: str):
    async def _call(*args, **kwargs):
        raise AssertionError(
            f"This test made a real OpenAI {what} call. Patch it explicitly "
            "(e.g. patch the service function or openai_client...create) — an "
            "unmocked call costs money, needs a key, and passes locally while "
            "failing in CI."
        )

    return _call


@pytest.fixture(autouse=True)
def forbid_real_llm_calls():
    """Fail loudly instead of quietly billing someone.

    Added after a route change made an existing test reach the real cover-letter
    generator: it passed on a machine with OPENAI_API_KEY set — spending real
    money on every run — and only surfaced as a 401 in CI. The failure mode that
    matters is not "CI is red", it is "a test silently calls a paid API and
    nobody notices", so this makes the unmocked path impossible to miss.

    Every service shares the one lazily-built client, so patching the methods on
    that object covers all of them. A test that patches the same path installs
    its own mock over this one for its duration, exactly as before.
    """
    with (
        patch(
            "app.services.llm_gateway.openai_client.chat.completions.create",
            new=_forbidden("chat completion"),
        ),
        patch(
            "app.services.llm_gateway.openai_client.embeddings.create",
            new=_forbidden("embedding"),
        ),
    ):
        yield
