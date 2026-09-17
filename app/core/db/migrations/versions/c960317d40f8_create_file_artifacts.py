"""create file artifacts

Revision ID: c960317d40f8
Revises: 4789fd8bf776
Create Date: 2026-09-17 16:28:02.746248

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c960317d40f8'
down_revision: str | Sequence[str] | None = '4789fd8bf776'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        'file_artifacts',
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('project_file_id', sa.Integer(), nullable=True),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column(
            'kind',
            sa.Enum(
                'canonical_dxf',
                'result_dxf',
                'plan_json',
                'report_json',
                'report_markdown',
                name='file_artifact_kind',
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            'format',
            sa.Enum(
                'dxf',
                'json',
                'markdown',
                name='file_artifact_format',
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column('download_name', sa.String(length=255), nullable=False),
        sa.Column('storage_key', sa.String(length=500), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('size_bytes > 0', name='ck_file_artifacts_size_bytes_positive'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_file_id'], ['project_files.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'kind', name='uq_file_artifacts_job_kind'),
        sa.UniqueConstraint('storage_key'),
    )
    op.create_index('ix_file_artifacts_job_id', 'file_artifacts', ['job_id'], unique=False)
    op.create_index('ix_file_artifacts_project_file_id', 'file_artifacts', ['project_file_id'], unique=False)
    op.create_index('ix_file_artifacts_project_id', 'file_artifacts', ['project_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index('ix_file_artifacts_project_id', table_name='file_artifacts')
    op.drop_index('ix_file_artifacts_project_file_id', table_name='file_artifacts')
    op.drop_index('ix_file_artifacts_job_id', table_name='file_artifacts')
    op.drop_table('file_artifacts')
