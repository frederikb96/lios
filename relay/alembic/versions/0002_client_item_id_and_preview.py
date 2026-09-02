"""client-supplied item id, sealed_preview column

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-02

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The sealed blob's AEAD associated data binds the item id, so the client must generate
    # it before the relay is ever contacted -- a server-side default would produce an id the
    # client's own seal never agreed to.
    op.alter_column("items", "id", server_default=None)
    op.add_column("items", sa.Column("sealed_preview", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("items", "sealed_preview")
    op.alter_column("items", "id", server_default=sa.text("gen_random_uuid()"))
