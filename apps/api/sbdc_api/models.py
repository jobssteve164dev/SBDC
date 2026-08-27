import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class PaperTask(Base):
    __tablename__ = "paper_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="created")
    stage_message: Mapped[str] = mapped_column(String(240), nullable=False, default="等待上传论文")
    evidence_level: Mapped[str] = mapped_column(String(8), nullable=False, default="L1")
    requested_checks: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    retention_policy: Mapped[str] = mapped_column(String(40), nullable=False, default="task_scoped")
    coverage_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_assets.id", name="fk_paper_tasks_source_file_id", use_alter=True), nullable=True
    )
    parse_attempt: Mapped[int] = mapped_column(nullable=False, default=0)
    parse_source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    assets: Mapped[list["DocumentAsset"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", foreign_keys="DocumentAsset.task_id"
    )


class DocumentAsset(Base):
    __tablename__ = "document_assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paper_tasks.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int | None] = mapped_column(nullable=True)
    license_status: Mapped[str] = mapped_column(String(40), nullable=False, default="user_provided")
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    retention_state: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[PaperTask] = relationship(back_populates="assets", foreign_keys=[task_id])


class ParsedDocument(Base):
    __tablename__ = "parsed_documents"
    __table_args__ = (UniqueConstraint("task_id", "source_sha256", name="uq_parse_task_source"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paper_tasks.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_assets.id", ondelete="CASCADE"))
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    authors: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    page_map: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    tei_storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    parser_name: Mapped[str] = mapped_column(String(40), nullable=False, default="grobid")
    parser_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReferenceSource(Base):
    __tablename__ = "reference_sources"
    __table_args__ = (UniqueConstraint("task_id", "ordinal", name="uq_reference_task_ordinal"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paper_tasks.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(nullable=False)
    raw_citation: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    authors: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    year: Mapped[str | None] = mapped_column(String(16), nullable=True)
    venue: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(300), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(30), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    page: Mapped[int | None] = mapped_column(nullable=True)
    bbox: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paper_tasks.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ParseRun(Base):
    __tablename__ = "parse_runs"
    __table_args__ = (UniqueConstraint("task_id", "source_sha256", "attempt", name="uq_parse_run_attempt"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("paper_tasks.id", ondelete="CASCADE"), index=True)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt: Mapped[int] = mapped_column(nullable=False)
    celery_task_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
