"""enable pgvector extension

Revision ID: c612a86ae86a
Revises: a5120eb2b1e0
Create Date: 2026-09-09 18:34:14.584780

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c612a86ae86a'
down_revision: str | Sequence[str] | None = 'a5120eb2b1e0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP EXTENSION IF EXISTS vector")
