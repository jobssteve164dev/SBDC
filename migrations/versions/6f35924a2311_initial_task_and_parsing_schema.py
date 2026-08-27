"""initial task and parsing schema

Revision ID: 6f35924a2311
Revises:
Create Date: 2026-08-27 01:11:21.499073
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '6f35924a2311'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "paper_tasks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("stage_message", sa.String(length=240), nullable=False),
        sa.Column("evidence_level", sa.String(length=8), nullable=False),
        sa.Column("requested_checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retention_policy", sa.String(length=40), nullable=False),
        sa.Column("coverage_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_file_id", sa.UUID(), nullable=True),
        sa.Column("parse_attempt", sa.Integer(), nullable=False),
        sa.Column("parse_source_sha256", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "document_assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("license_status", sa.String(length=40), nullable=False),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retention_state", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["paper_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(op.f("ix_document_assets_task_id"), "document_assets", ["task_id"], unique=False)
    op.create_foreign_key("fk_paper_tasks_source_file_id", "paper_tasks", "document_assets", ["source_file_id"], ["id"], use_alter=True)
    op.create_table(
        "audit_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["paper_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_task_id"), "audit_events", ["task_id"], unique=False)
    op.create_table(
        "parse_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("celery_task_id", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["paper_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("celery_task_id"),
        sa.UniqueConstraint("task_id", "source_sha256", "attempt", name="uq_parse_run_attempt"),
    )
    op.create_index(op.f("ix_parse_runs_task_id"), "parse_runs", ["task_id"], unique=False)
    op.create_table(
        "parsed_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("authors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("page_map", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tei_storage_key", sa.String(length=500), nullable=False),
        sa.Column("parser_name", sa.String(length=40), nullable=False),
        sa.Column("parser_version", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["document_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["paper_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "source_sha256", name="uq_parse_task_source"),
    )
    op.create_index(op.f("ix_parsed_documents_task_id"), "parsed_documents", ["task_id"], unique=False)
    op.create_table(
        "reference_sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("raw_citation", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("authors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("year", sa.String(length=16), nullable=True),
        sa.Column("venue", sa.Text(), nullable=True),
        sa.Column("doi", sa.String(length=300), nullable=True),
        sa.Column("parse_status", sa.String(length=30), nullable=False),
        sa.Column("failure_reason", sa.String(length=120), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["paper_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "ordinal", name="uq_reference_task_ordinal"),
    )
    op.create_index(op.f("ix_reference_sources_task_id"), "reference_sources", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reference_sources_task_id"), table_name="reference_sources")
    op.drop_table("reference_sources")
    op.drop_index(op.f("ix_parsed_documents_task_id"), table_name="parsed_documents")
    op.drop_table("parsed_documents")
    op.drop_index(op.f("ix_parse_runs_task_id"), table_name="parse_runs")
    op.drop_table("parse_runs")
    op.drop_index(op.f("ix_audit_events_task_id"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_constraint("fk_paper_tasks_source_file_id", "paper_tasks", type_="foreignkey")
    op.drop_index(op.f("ix_document_assets_task_id"), table_name="document_assets")
    op.drop_table("document_assets")
    op.drop_table("paper_tasks")
