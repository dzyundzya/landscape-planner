"""create plans

Revision ID: 5785de4dcaac
Revises: 5466c2b65a34
Create Date: 2026-09-17 17:06:37.369673

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5785de4dcaac'
down_revision: str | Sequence[str] | None = '5466c2b65a34'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        'plans',
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('project_file_id', sa.Integer(), nullable=False),
        sa.Column('analysis_id', sa.Integer(), nullable=False),
        sa.Column('config_snapshot_id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'needs_verification',
                'verified',
                'invalid',
                name='plan_status',
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column('generator_version', sa.String(length=100), nullable=False),
        sa.Column('generation_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('revision > 0', name='ck_plans_revision_positive'),
        sa.ForeignKeyConstraint(['analysis_id'], ['analyses.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['config_snapshot_id'], ['config_snapshots.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_file_id'], ['project_files.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', name='uq_plans_job_id'),
    )
    op.create_index('ix_plans_analysis_id', 'plans', ['analysis_id'], unique=False)
    op.create_index('ix_plans_config_snapshot_id', 'plans', ['config_snapshot_id'], unique=False)
    op.create_index('ix_plans_project_file_id', 'plans', ['project_file_id'], unique=False)
    op.create_index('ix_plans_project_id', 'plans', ['project_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index('ix_plans_project_id', table_name='plans')
    op.drop_index('ix_plans_project_file_id', table_name='plans')
    op.drop_index('ix_plans_config_snapshot_id', table_name='plans')
    op.drop_index('ix_plans_analysis_id', table_name='plans')
    op.drop_table('plans')
