"""create analyses

Revision ID: 60d2bafebd4e
Revises: c960317d40f8
Create Date: 2026-09-17 16:39:18.565061

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '60d2bafebd4e'
down_revision: str | Sequence[str] | None = 'c960317d40f8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        'analyses',
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('project_file_id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('schema_version', sa.Integer(), nullable=False),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('schema_version > 0', name='ck_analyses_schema_version_positive'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_file_id'], ['project_files.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', name='uq_analyses_job_id'),
    )
    op.create_index('ix_analyses_project_file_id', 'analyses', ['project_file_id'], unique=False)
    op.create_index('ix_analyses_project_id', 'analyses', ['project_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index('ix_analyses_project_id', table_name='analyses')
    op.drop_index('ix_analyses_project_file_id', table_name='analyses')
    op.drop_table('analyses')
