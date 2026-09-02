"""initial schema: devices, pairing_sessions, items, item_recipients, item_acks

Revision ID: 0001
Revises:
Create Date: 2026-09-02

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("apns_token", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("token_hash", name="uq_devices_token_hash"),
    )
    op.create_index("ix_devices_token_hash", "devices", ["token_hash"])

    op.create_table(
        "pairing_sessions",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "requested_by_device_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("code_hash", name="uq_pairing_sessions_code_hash"),
    )
    op.create_index("ix_pairing_sessions_code_hash", "pairing_sessions", ["code_hash"])

    op.create_table(
        "items",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "sender_device_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "target_device_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("sealed_blob", sa.LargeBinary(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_items_created_at", "items", ["created_at"])

    op.create_table(
        "item_recipients",
        sa.Column(
            "item_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "device_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True,
        ),
    )

    op.create_table(
        "item_acks",
        sa.Column(
            "item_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "device_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "acked_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("item_acks")
    op.drop_table("item_recipients")
    op.drop_index("ix_items_created_at", table_name="items")
    op.drop_table("items")
    op.drop_index("ix_pairing_sessions_code_hash", table_name="pairing_sessions")
    op.drop_table("pairing_sessions")
    op.drop_index("ix_devices_token_hash", table_name="devices")
    op.drop_table("devices")
