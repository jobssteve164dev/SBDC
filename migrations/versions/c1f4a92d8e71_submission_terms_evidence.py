"""store submission terms acceptance evidence

Revision ID: c1f4a92d8e71
Revises: 9a3d64e19d20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c1f4a92d8e71"
down_revision: str | None = "9a3d64e19d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Historical rows remain null because they predate this exact agreement text.
    op.add_column("research_submissions", sa.Column("terms_version", sa.String(length=40), nullable=True))
    op.add_column("research_submissions", sa.Column("terms_locale", sa.String(length=8), nullable=True))
    op.add_column("research_submissions", sa.Column("terms_notice_sha256", sa.String(length=64), nullable=True))
    op.add_column("research_submissions", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("research_submissions", "terms_accepted_at")
    op.drop_column("research_submissions", "terms_notice_sha256")
    op.drop_column("research_submissions", "terms_locale")
    op.drop_column("research_submissions", "terms_version")
