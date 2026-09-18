"""create exports

Revision ID: e31f9a6c2b74
Revises: b42c8e7a1d3f
Create Date: 2026-09-17 20:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e31f9a6c2b74'
down_revision: str | Sequence[str] | None = 'b42c8e7a1d3f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        'exports',
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('plan_revision', sa.Integer(), nullable=False),
        sa.Column('validation_id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('export_version', sa.String(length=100), nullable=False),
        sa.Column('manifest', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('plan_revision > 0', name='ck_exports_plan_revision_positive'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['validation_id'], ['plan_validations.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', name='uq_exports_job_id'),
    )
    op.create_index('ix_exports_plan_id', 'exports', ['plan_id'], unique=False)
    op.create_index('ix_exports_project_id', 'exports', ['project_id'], unique=False)
    op.create_index('ix_exports_validation_id', 'exports', ['validation_id'], unique=False)
    op.add_column('file_artifacts', sa.Column('export_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_file_artifacts_export_id_exports',
        'file_artifacts',
        'exports',
        ['export_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_file_artifacts_export_id', 'file_artifacts', ['export_id'], unique=False)
    op.create_unique_constraint(
        'uq_file_artifacts_export_kind',
        'file_artifacts',
        ['export_id', 'kind'],
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint('uq_file_artifacts_export_kind', 'file_artifacts', type_='unique')
    op.drop_index('ix_file_artifacts_export_id', table_name='file_artifacts')
    op.drop_constraint('fk_file_artifacts_export_id_exports', 'file_artifacts', type_='foreignkey')
    op.drop_column('file_artifacts', 'export_id')
    op.drop_index('ix_exports_validation_id', table_name='exports')
    op.drop_index('ix_exports_project_id', table_name='exports')
    op.drop_index('ix_exports_plan_id', table_name='exports')
    op.drop_table('exports')
