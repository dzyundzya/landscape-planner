"""create jobs

Revision ID: 4789fd8bf776
Revises: a8bd5e0ad889
Create Date: 2026-09-17 15:39:37.978030

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4789fd8bf776'
down_revision: str | Sequence[str] | None = 'a8bd5e0ad889'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        'jobs',
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('project_file_id', sa.Integer(), nullable=True),
        sa.Column(
            'type',
            sa.Enum(
                'convert_dwf',
                'analyze',
                'generate_plan',
                'export',
                'agent_request',
                name='job_type',
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum(
                'queued',
                'running',
                'succeeded',
                'failed',
                name='job_status',
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column('stage', sa.String(length=100), nullable=True),
        sa.Column('input_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['project_file_id'], ['project_files.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_jobs_project_file_id', 'jobs', ['project_file_id'], unique=False)
    op.create_index('ix_jobs_project_id', 'jobs', ['project_id'], unique=False)
    op.create_index('ix_jobs_queue', 'jobs', ['status', 'created_at', 'id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index('ix_jobs_queue', table_name='jobs')
    op.drop_index('ix_jobs_project_id', table_name='jobs')
    op.drop_index('ix_jobs_project_file_id', table_name='jobs')
    op.drop_table('jobs')
