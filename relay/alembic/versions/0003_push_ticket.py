"""push ticket instead of raw APNs token

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-13

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A raw APNs token cannot be turned into a ticket here -- only the phone can register
    # with the push relay -- so the tokens are dropped and each iOS device uploads a ticket
    # the next time its app starts.
    op.add_column("devices", sa.Column("push_ticket", sa.Text(), nullable=True))
    op.drop_column("devices", "apns_token")


def downgrade() -> None:
    op.add_column("devices", sa.Column("apns_token", sa.String(length=200), nullable=True))
    op.drop_column("devices", "push_ticket")
