"""support anonymous and public submissions

Revision ID: 9a3d64e19d20
Revises: 7b1d9a45c2ef
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "9a3d64e19d20"
down_revision: str | None = "7b1d9a45c2ef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("research_submissions", sa.Column("contact_email", sa.String(length=254), nullable=True))
    op.execute(sa.text(
        "UPDATE research_submissions AS submission SET contact_email = public_users.email "
        "FROM public_users WHERE submission.submitted_by_id = public_users.id"
    ))
    op.alter_column("research_submissions", "contact_email", nullable=False)
    op.alter_column("research_submissions", "submitted_by_id", existing_type=sa.UUID(), nullable=True)
    op.add_column("research_submissions", sa.Column("is_public", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("research_submissions", sa.Column("review_outcome", sa.String(length=40), nullable=True))
    op.add_column("research_submissions", sa.Column("review_summary", sa.Text(), nullable=True))
    op.add_column("research_submissions", sa.Column("review_published", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("research_submissions", sa.Column("review_published_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_research_submissions_is_public", "research_submissions", ["is_public"])
    op.create_index("ix_research_submissions_review_published", "research_submissions", ["review_published"])


def downgrade() -> None:
    raise RuntimeError(
        "This migration cannot be downgraded without deleting anonymous submissions and publication decisions."
    )
