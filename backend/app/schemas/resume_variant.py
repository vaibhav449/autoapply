from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResumeVariantCreate(BaseModel):
    role_label: str
    emphasis_note: str | None = None


class ResumeVariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role_label: str
    emphasis_note: str | None
    generated_content: str
    unverified_claims: list[str]
    created_at: datetime
