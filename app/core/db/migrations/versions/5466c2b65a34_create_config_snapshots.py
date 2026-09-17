"""create config snapshots

Revision ID: 5466c2b65a34
Revises: 60d2bafebd4e
Create Date: 2026-09-17 16:51:21.538190

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5466c2b65a34'
down_revision: str | Sequence[str] | None = '60d2bafebd4e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        'config_snapshots',
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('analysis_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('schema_version', sa.Integer(), nullable=False),
        sa.Column(
            'coordinate_unit',
            sa.Enum(
                'millimeter',
                'centimeter',
                'meter',
                'kilometer',
                'inch',
                'foot',
                'yard',
                name='coordinate_unit',
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column('unit_scale_to_meters', sa.Numeric(precision=18, scale=9), nullable=False),
        sa.Column('boundary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('layer_mappings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('generation', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'rules_status',
            sa.Enum(
                'needs_verification',
                'verified',
                name='normative_rules_status',
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column('rules_version', sa.String(length=100), nullable=True),
        sa.Column('rules_sha256', sa.String(length=64), nullable=True),
        sa.Column('content_sha256', sa.String(length=64), nullable=False),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('schema_version > 0', name='ck_config_snapshots_schema_version_positive'),
        sa.CheckConstraint('unit_scale_to_meters > 0', name='ck_config_snapshots_unit_scale_positive'),
        sa.CheckConstraint('version > 0', name='ck_config_snapshots_version_positive'),
        sa.ForeignKeyConstraint(['analysis_id'], ['analyses.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'content_sha256', name='uq_config_snapshots_project_content'),
        sa.UniqueConstraint('project_id', 'version', name='uq_config_snapshots_project_version'),
    )
    op.create_index('ix_config_snapshots_analysis_id', 'config_snapshots', ['analysis_id'], unique=False)
    op.create_index('ix_config_snapshots_project_id', 'config_snapshots', ['project_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index('ix_config_snapshots_project_id', table_name='config_snapshots')
    op.drop_index('ix_config_snapshots_analysis_id', table_name='config_snapshots')
    op.drop_table('config_snapshots')
