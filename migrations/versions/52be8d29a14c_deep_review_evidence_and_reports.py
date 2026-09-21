"""deep review evidence and reports

Revision ID: 52be8d29a14c
Revises: c1f4a92d8e71
Create Date: 2026-09-21 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "52be8d29a14c"
down_revision: Union[str, Sequence[str], None] = "c1f4a92d8e71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("paper_tasks", sa.Column("review_attempt", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("paper_tasks", sa.Column("review_source_sha256", sa.String(length=64), nullable=True))
    op.add_column("reference_sources", sa.Column("metadata_status", sa.String(length=30), nullable=False, server_default="not_checked"))
    op.add_column("reference_sources", sa.Column("full_text_status", sa.String(length=30), nullable=False, server_default="not_checked"))
    op.add_column("reference_sources", sa.Column("full_text_asset_id", sa.UUID(), nullable=True))
    op.add_column("reference_sources", sa.Column("access_url", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_reference_sources_full_text_asset_id", "reference_sources", "document_assets",
        ["full_text_asset_id"], ["id"], ondelete="SET NULL",
    )
    op.create_table(
        "review_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("method_version", sa.String(length=80), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("celery_task_id", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["paper_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("celery_task_id"),
        sa.UniqueConstraint("task_id", "source_sha256", "attempt", name="uq_review_run_attempt"),
    )
    op.create_index(op.f("ix_review_runs_task_id"), "review_runs", ["task_id"], unique=False)
    op.create_table(
        "evidence_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("subject_location", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_location", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("subject_excerpt", sa.Text(), nullable=False),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("method", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("limitations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifacts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_version", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["paper_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "fingerprint", "evidence_version", name="uq_evidence_task_fingerprint_version"),
    )
    op.create_index(op.f("ix_evidence_items_task_id"), "evidence_items", ["task_id"], unique=False)
    op.create_table(
        "evidence_decisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("evidence_id", sa.UUID(), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reviewer_id", sa.String(length=120), nullable=False),
        sa.Column("evidence_version", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["paper_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evidence_decisions_task_id"), "evidence_decisions", ["task_id"], unique=False)
    op.create_index(op.f("ix_evidence_decisions_evidence_id"), "evidence_decisions", ["evidence_id"], unique=False)
    op.create_table(
        "review_reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("asset_id", sa.UUID(), nullable=False),
        sa.Column("evidence_version", sa.String(length=160), nullable=False),
        sa.Column("coverage_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["document_assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["paper_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "evidence_version", name="uq_report_task_version"),
    )
    op.create_index(op.f("ix_review_reports_task_id"), "review_reports", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_review_reports_task_id"), table_name="review_reports")
    op.drop_table("review_reports")
    op.drop_index(op.f("ix_evidence_decisions_evidence_id"), table_name="evidence_decisions")
    op.drop_index(op.f("ix_evidence_decisions_task_id"), table_name="evidence_decisions")
    op.drop_table("evidence_decisions")
    op.drop_index(op.f("ix_evidence_items_task_id"), table_name="evidence_items")
    op.drop_table("evidence_items")
    op.drop_index(op.f("ix_review_runs_task_id"), table_name="review_runs")
    op.drop_table("review_runs")
    op.drop_constraint("fk_reference_sources_full_text_asset_id", "reference_sources", type_="foreignkey")
    op.drop_column("reference_sources", "access_url")
    op.drop_column("reference_sources", "full_text_asset_id")
    op.drop_column("reference_sources", "full_text_status")
    op.drop_column("reference_sources", "metadata_status")
    op.drop_column("paper_tasks", "review_source_sha256")
    op.drop_column("paper_tasks", "review_attempt")
