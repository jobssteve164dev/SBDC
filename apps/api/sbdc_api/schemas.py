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
    metadata_status: str
    full_text_status: str


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
    report_asset: AssetOut | None = None


class ParseAccepted(BaseModel):
    task_id: uuid.UUID
    status: str
    enqueued: bool


class CheckAccepted(ParseAccepted):
    pass


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(confirmed|needs_material|insufficient|reasonable)$")
    reason: str = Field(min_length=10, max_length=2000)


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    evidence_id: uuid.UUID
    decision: str
    reason: str
    reviewer_id: str
    evidence_version: str
    created_at: datetime


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    category: str
    status: str
    severity: str
    confidence: float
    subject_location: dict[str, Any]
    source_location: dict[str, Any] | None
    subject_excerpt: str
    source_excerpt: str | None
    explanation: str
    method: dict[str, Any]
    limitations: list[str]
    artifacts: list[str]
    evidence_version: str
    created_at: datetime
    decision: DecisionOut | None = None


class ReportOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    asset_id: uuid.UUID
    evidence_version: str
    download_url: str
    created_at: datetime


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
