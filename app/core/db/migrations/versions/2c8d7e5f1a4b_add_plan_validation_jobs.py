"""add plan validation jobs

Revision ID: 2c8d7e5f1a4b
Revises: 91a7c4d2e6f8
Create Date: 2026-09-18 17:00:00.000000

"""
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '2c8d7e5f1a4b'
down_revision: str | Sequence[str] | None = '91a7c4d2e6f8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.drop_constraint('job_type', 'jobs', type_='check')
    op.create_check_constraint(
        'job_type',
        'jobs',
        "type IN ('convert_dwf', 'analyze', 'generate_plan', 'validate_plan', 'export', 'agent_request')",
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint('job_type', 'jobs', type_='check')
    op.create_check_constraint(
        'job_type',
        'jobs',
        "type IN ('convert_dwf', 'analyze', 'generate_plan', 'export', 'agent_request')",
    )
