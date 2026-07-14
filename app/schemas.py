from uuid import UUID

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=1000,
    )
    limit: int = Field(
        default=3,
        ge=1,
        le=10,
    )

class AskRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=1000,
    )


class SourceResponse(BaseModel):
    document_id: UUID
    filename: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceResponse]
