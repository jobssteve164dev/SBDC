from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CoverageSummary(BaseModel):
    references_total: int = 0
    references_parsed: int = 0
    references_failed: int = 0
    failure_reasons: dict[str, int] = Field(default_factory=dict)
    body_sections: int = 0
    located_sections: int = 0


class DocumentLocation(BaseModel):
    document_id: str
    page: int | None = None
    bbox: list[float] | None = None
    char_start: int | None = None
    char_end: int | None = None


class EvidenceItem(BaseModel):
    id: str
    task_id: str
    category: str
    status: Literal["needs_review", "verified_anomaly", "insufficient", "reasonable"]
    severity: Literal["low", "medium", "high"]
    confidence: float = Field(ge=0, le=1)
    subject_location: DocumentLocation
    source_location: DocumentLocation | None = None
    subject_excerpt: str
    source_excerpt: str | None = None
    method: dict[str, Any]
    limitations: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    created_at: datetime


class ReviewDecision(BaseModel):
    evidence_id: str
    decision: Literal["confirmed", "needs_material", "insufficient", "reasonable"]
    reason: str
    reviewer_id: str
    evidence_version: str
    created_at: datetime
