from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DraftAnswerCreate(BaseModel):
    question_text: str


class DraftAnswerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    question_text: str
    answer_text: str
    unverified_claims: list[str]
    created_at: datetime
