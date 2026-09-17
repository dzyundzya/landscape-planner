"""create plantings

Revision ID: 6edc02e9434e
Revises: 5785de4dcaac
Create Date: 2026-09-17 18:33:29.603279

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6edc02e9434e'
down_revision: str | Sequence[str] | None = '5785de4dcaac'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        'plantings',
        sa.Column('public_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column(
            'type',
            sa.Enum(
                'tree',
                'bush',
                name='planting_type',
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            'source',
            sa.Enum(
                'generated',
                'manual',
                name='planting_source',
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column('x_m', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('y_m', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('species', sa.String(length=255), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('public_id'),
    )
    op.create_index('ix_plantings_plan_id', 'plantings', ['plan_id'], unique=False)
    op.create_index('ix_plantings_plan_type', 'plantings', ['plan_id', 'type'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index('ix_plantings_plan_type', table_name='plantings')
    op.drop_index('ix_plantings_plan_id', table_name='plantings')
    op.drop_table('plantings')
