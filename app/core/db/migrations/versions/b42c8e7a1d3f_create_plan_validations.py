"""create plan validations

Revision ID: b42c8e7a1d3f
Revises: 6edc02e9434e
Create Date: 2026-09-17 19:15:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b42c8e7a1d3f'
down_revision: str | Sequence[str] | None = '6edc02e9434e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        'plan_validations',
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('plan_revision', sa.Integer(), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'passed',
                'failed',
                'needs_verification',
                name='validation_status',
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column('validator_version', sa.String(length=100), nullable=False),
        sa.Column('checks', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'rules_status',
            sa.Enum(
                'needs_verification',
                'verified',
                name='validation_rules_status',
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column('rules_version', sa.String(length=100), nullable=True),
        sa.Column('rules_sha256', sa.String(length=64), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('plan_revision > 0', name='ck_plan_validations_revision_positive'),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('plan_id', 'plan_revision', name='uq_plan_validations_plan_revision'),
    )
    op.create_index('ix_plan_validations_plan_id', 'plan_validations', ['plan_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index('ix_plan_validations_plan_id', table_name='plan_validations')
    op.drop_table('plan_validations')
