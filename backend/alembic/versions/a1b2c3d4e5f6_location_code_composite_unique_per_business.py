"""location_code_composite_unique_per_business

Replace the global unique constraint on business_locations.location_code with a
composite unique constraint (location_code, business_id) so that the same
location code can be reused across different businesses.

Revision ID: a1b2c3d4e5f6
Revises: fc51a3928318
Create Date: 2026-07-03 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "fc51a3928318"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old global unique index on location_code
    op.drop_index(
        "ix_business_locations_location_code",
        table_name="business_locations",
        if_exists=True,
    )
    # Drop old global unique constraint on location_code (created in original migration)
    op.drop_constraint(
        "uq_business_locations_location_code",
        "business_locations",
        type_="unique",
    )
    # Create a non-unique index on location_code for query performance
    op.create_index(
        "ix_business_locations_location_code",
        "business_locations",
        ["location_code"],
        unique=False,
    )
    # Add composite unique constraint: (location_code, business_id)
    op.create_unique_constraint(
        "uq_business_locations_code_business",
        "business_locations",
        ["location_code", "business_id"],
    )


def downgrade() -> None:
    # Remove composite constraint
    op.drop_constraint(
        "uq_business_locations_code_business",
        "business_locations",
        type_="unique",
    )
    # Remove non-unique index
    op.drop_index(
        "ix_business_locations_location_code",
        table_name="business_locations",
    )
    # Restore old global unique index
    op.create_index(
        "ix_business_locations_location_code",
        "business_locations",
        ["location_code"],
        unique=True,
    )
    # Restore old global unique constraint
    op.create_unique_constraint(
        "uq_business_locations_location_code",
        "business_locations",
        ["location_code"],
    )
