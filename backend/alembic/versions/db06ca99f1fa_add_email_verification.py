"""add email verification

Revision ID: db06ca99f1fa
Revises: 1a76f66ca128
Create Date: 2026-09-09 10:00:00.000000

Adds `email_verified` to users (backfilled true for every pre-existing
row -- only the self-service /auth/onboard signup path requires clicking
a verification link going forward, admin-created users are pre-verified,
and nobody already using the app should be locked out) and a new
email_verification_tokens table mirroring password_reset_tokens'
existing shape exactly (see e276548633ad_add_password_reset_tokens_table.py).

Idempotent (existence-checked per statement), matching the established
pattern -- see 1a76f66ca128_add_business_id_to_fx_exposures.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "db06ca99f1fa"
down_revision: Union[str, None] = "1a76f66ca128"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from src.core.migration_utils import has_column, has_table

    insp = sa.inspect(op.get_bind())

    if not has_column("users", "email_verified", insp=insp):
        op.add_column(
            "users",
            sa.Column(
                "email_verified",
                sa.Boolean(),
                server_default="false",
                nullable=False,
            ),
        )
        # Backfill: every row that existed before this migration predates the
        # feature and must not be locked out of login.
        op.execute("UPDATE users SET email_verified = true")

    if not has_table("email_verification_tokens", insp=insp):
        op.create_table(
            "email_verification_tokens",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Uuid(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("token", sa.String(64), unique=True, index=True, nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used", sa.Boolean(), server_default="false", nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    from src.core.migration_utils import has_column, has_table

    insp = sa.inspect(op.get_bind())

    if has_table("email_verification_tokens", insp=insp):
        op.drop_table("email_verification_tokens")
    if has_column("users", "email_verified", insp=insp):
        op.drop_column("users", "email_verified")
