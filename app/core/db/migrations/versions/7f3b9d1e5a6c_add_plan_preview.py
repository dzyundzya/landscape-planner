"""add plan preview

Revision ID: 7f3b9d1e5a6c
Revises: 2c8d7e5f1a4b
Create Date: 2026-09-18 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '7f3b9d1e5a6c'
down_revision: str | Sequence[str] | None = '2c8d7e5f1a4b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        'plans',
        sa.Column('preview_geometry', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column('plans', 'preview_geometry')
