"""Initialize the empty M0 schema baseline.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Establish the M0 migration baseline without business tables."""


def downgrade() -> None:
    """Remove the M0 migration baseline without business tables."""
