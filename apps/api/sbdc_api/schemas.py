import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    evidence_level: str = Field(default="L1", pattern="^L1$")
    retention_policy: str = Field(default="task_scoped", pattern="^task_scoped$")


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    task_id: uuid.UUID
    role: str
    sha256: str
    media_type: str
    size_bytes: int
    page_count: int | None
    created_at: datetime


class ReferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ordinal: int
    raw_citation: str
    title: str | None
    authors: list[str]
    year: str | None
    venue: str | None
    doi: str | None
    parse_status: str
    failure_reason: str | None
    confidence: float | None
    page: int | None
    bbox: list[float] | None


class ParsedDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    title: str | None
    authors: list[str]
    abstract: str | None
    language: str | None
    sections: list[dict[str, Any]]
    page_map: list[dict[str, Any]]
    parser_name: str
    parser_version: str | None


class TaskOut(BaseModel):
    id: uuid.UUID
    status: str
    stage_message: str
    evidence_level: str
    retention_policy: str
    coverage_summary: dict[str, Any]
    source_file_id: uuid.UUID | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    source_asset: AssetOut | None = None
    document: ParsedDocumentOut | None = None
    references: list[ReferenceOut] = Field(default_factory=list)


class ParseAccepted(BaseModel):
    task_id: uuid.UUID
    status: str
    enqueued: bool


class PublicUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    authors: str | None
    reason: str
    status: str
    size_bytes: int
    page_count: int
    created_at: datetime


class PublicSubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    authors: str | None
    reason: str
    created_at: datetime


class PublicReviewNoticeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    authors: str | None
    review_outcome: str
    review_summary: str
    review_published_at: datetime


class ReviewerSubmissionOut(SubmissionOut):
    submitter_email: str
    is_public: bool
    review_outcome: str | None
    review_summary: str | None
    review_published: bool
    review_published_at: datetime | None
    terms_version: str | None
    terms_locale: str | None
    terms_notice_sha256: str | None
    terms_accepted_at: datetime | None
