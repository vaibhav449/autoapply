from pydantic import BaseModel

from app.automation.adapters.greenhouse import FillStatus


class FillFormResultOut(BaseModel):
    status: FillStatus
    filled_fields: dict[str, str]
    skipped_fields: list[str]
    # base64-encoded PNG, not raw bytes — this is a one-shot review artifact
    # returned inline with the rest of the result, not a stored resource with
    # its own URL the way a resume PDF is.
    screenshot_base64: str | None
