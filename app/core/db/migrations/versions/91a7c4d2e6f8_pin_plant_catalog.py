"""pin plant catalog

Revision ID: 91a7c4d2e6f8
Revises: e31f9a6c2b74
Create Date: 2026-09-18 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '91a7c4d2e6f8'
down_revision: str | Sequence[str] | None = 'e31f9a6c2b74'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TERRITORY_VALUES = (
    'courtyard',
    'preschool',
    'education_and_sport',
    'healthcare',
    'roads',
    'public_and_commercial',
    'parks_and_public_green',
    'industrial_and_protection',
)
CATALOG_STATUS_VALUES = ('needs_verification', 'verified')


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        'config_snapshots',
        sa.Column(
            'territory_type',
            sa.Enum(
                *TERRITORY_VALUES,
                name='territory_type',
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        'config_snapshots',
        sa.Column(
            'plant_catalog_status',
            sa.Enum(
                *CATALOG_STATUS_VALUES,
                name='plant_catalog_status',
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
    )
    op.add_column('config_snapshots', sa.Column('plant_catalog_version', sa.String(length=100), nullable=True))
    op.add_column('config_snapshots', sa.Column('plant_catalog_sha256', sa.String(length=64), nullable=True))

    op.add_column(
        'plan_validations',
        sa.Column(
            'plant_catalog_status',
            sa.Enum(
                *CATALOG_STATUS_VALUES,
                name='validation_plant_catalog_status',
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
    )
    op.add_column('plan_validations', sa.Column('plant_catalog_version', sa.String(length=100), nullable=True))
    op.add_column('plan_validations', sa.Column('plant_catalog_sha256', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column('plan_validations', 'plant_catalog_sha256')
    op.drop_column('plan_validations', 'plant_catalog_version')
    op.drop_column('plan_validations', 'plant_catalog_status')
    op.drop_column('config_snapshots', 'plant_catalog_sha256')
    op.drop_column('config_snapshots', 'plant_catalog_version')
    op.drop_column('config_snapshots', 'plant_catalog_status')
    op.drop_column('config_snapshots', 'territory_type')
