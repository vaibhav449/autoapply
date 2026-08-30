from abc import ABC, abstractmethod
from typing import Any


class ATSAdapter(ABC):
    """Interface every ATS-specific form-filling adapter must implement."""

    @abstractmethod
    async def matches(self, application_url: str) -> bool:
        """Return True if this adapter knows how to handle the given URL."""

    @abstractmethod
    async def fill(self, application_url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Fill the application form and return the resulting field state for review."""
