"""`pg` tests for the retention prune pass."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from lios_relay.config import RetentionConfig
from lios_relay.database.connection import DatabaseConnection
from lios_relay.database.models import Item
from lios_relay.database.repository import (
    ack_item,
    create_device,
    create_item,
    generate_device_token,
    get_device_by_token,
)
from lios_relay.retention import run_prune_pass


async def _make_two_devices(db: DatabaseConnection) -> tuple[str, str]:
    laptop_token, phone_token = generate_device_token(), generate_device_token()
    async with db.session() as session:
        await create_device(session, display_name="Laptop", platform="linux", token=laptop_token)
        await create_device(session, display_name="Phone", platform="ios", token=phone_token)
    return laptop_token, phone_token


async def test_prune_deletes_items_past_max_age(migrated_db: DatabaseConnection) -> None:
    laptop_token, phone_token = await _make_two_devices(migrated_db)

    async with migrated_db.session() as session:
        laptop = await get_device_by_token(session, laptop_token)
        phone = await get_device_by_token(session, phone_token)
        assert laptop and phone
        item = await create_item(
            session, item_id=uuid.uuid4(), sender_device_id=laptop.id, target_device_id=None,
            sealed_blob=b"old news", sealed_preview=None, recipient_ids=[phone.id],
        )
        item_id = item.id

    # Backdate it past the retention window -- the only way to exercise the age prune
    # without sleeping for real days in a test.
    async with migrated_db.session() as session:
        await session.execute(
            update(Item).where(Item.id == item_id)
            .values(created_at=datetime.now(UTC) - timedelta(days=30))
        )

    await run_prune_pass(
        migrated_db, RetentionConfig(max_items=50, max_age_days=7, prune_interval_seconds=300)
    )

    async with migrated_db.session() as session:
        assert await session.get(Item, item_id) is None


async def test_prune_keeps_only_the_newest_max_items(migrated_db: DatabaseConnection) -> None:
    laptop_token, phone_token = await _make_two_devices(migrated_db)
    async with migrated_db.session() as session:
        laptop = await get_device_by_token(session, laptop_token)
        phone = await get_device_by_token(session, phone_token)
        assert laptop and phone
        for i in range(5):
            await create_item(
                session, item_id=uuid.uuid4(), sender_device_id=laptop.id, target_device_id=None,
                sealed_blob=f"item {i}".encode(), sealed_preview=None, recipient_ids=[phone.id],
            )

    await run_prune_pass(
        migrated_db, RetentionConfig(max_items=2, max_age_days=7, prune_interval_seconds=300)
    )

    async with migrated_db.session() as session:
        remaining = (await session.execute(Item.__table__.select())).all()
    assert len(remaining) == 2


async def test_prune_deletes_an_item_once_every_recipient_and_the_sender_have_acked(
    migrated_db: DatabaseConnection,
) -> None:
    laptop_token, phone_token = await _make_two_devices(migrated_db)
    async with migrated_db.session() as session:
        laptop = await get_device_by_token(session, laptop_token)
        phone = await get_device_by_token(session, phone_token)
        assert laptop and phone
        item = await create_item(
            session, item_id=uuid.uuid4(), sender_device_id=laptop.id, target_device_id=None,
            sealed_blob=b"acked already", sealed_preview=None, recipient_ids=[phone.id],
        )
        item_id = item.id
        await ack_item(session, item_id, phone.id)
        await ack_item(session, item_id, laptop.id)

    await run_prune_pass(
        migrated_db, RetentionConfig(max_items=50, max_age_days=7, prune_interval_seconds=300)
    )

    async with migrated_db.session() as session:
        assert await session.get(Item, item_id) is None


async def test_prune_keeps_an_unacked_item_within_retention(
    migrated_db: DatabaseConnection,
) -> None:
    laptop_token, phone_token = await _make_two_devices(migrated_db)
    async with migrated_db.session() as session:
        laptop = await get_device_by_token(session, laptop_token)
        phone = await get_device_by_token(session, phone_token)
        assert laptop and phone
        item = await create_item(
            session, item_id=uuid.uuid4(), sender_device_id=laptop.id, target_device_id=None,
            sealed_blob=b"still waiting", sealed_preview=None, recipient_ids=[phone.id],
        )
        item_id = item.id

    await run_prune_pass(
        migrated_db, RetentionConfig(max_items=50, max_age_days=7, prune_interval_seconds=300)
    )

    async with migrated_db.session() as session:
        assert await session.get(Item, item_id) is not None


async def test_prune_keeps_an_item_the_recipient_acked_but_the_sender_did_not(
    migrated_db: DatabaseConnection,
) -> None:
    """Every recipient having acked is not enough on its own -- the sender must ack too,
    since that ack is what makes the item's own upload disappear from `sent=true`."""
    laptop_token, phone_token = await _make_two_devices(migrated_db)
    async with migrated_db.session() as session:
        laptop = await get_device_by_token(session, laptop_token)
        phone = await get_device_by_token(session, phone_token)
        assert laptop and phone
        item = await create_item(
            session, item_id=uuid.uuid4(), sender_device_id=laptop.id, target_device_id=None,
            sealed_blob=b"recipient acked, sender did not", sealed_preview=None,
            recipient_ids=[phone.id],
        )
        item_id = item.id
        await ack_item(session, item_id, phone.id)

    await run_prune_pass(
        migrated_db, RetentionConfig(max_items=50, max_age_days=7, prune_interval_seconds=300)
    )

    async with migrated_db.session() as session:
        assert await session.get(Item, item_id) is not None


async def test_prune_keeps_a_senders_solo_upload_until_the_sender_acks(
    migrated_db: DatabaseConnection,
) -> None:
    """An item with an empty recipient snapshot (the sender was the only paired device at
    creation time) is vacuously fully acked by its recipients, but must still wait on the
    sender's own ack -- otherwise a device could never list its own just-sent item back."""
    laptop_token, _ = await _make_two_devices(migrated_db)
    async with migrated_db.session() as session:
        laptop = await get_device_by_token(session, laptop_token)
        assert laptop
        item = await create_item(
            session, item_id=uuid.uuid4(), sender_device_id=laptop.id, target_device_id=None,
            sealed_blob=b"nobody else was paired yet", sealed_preview=None, recipient_ids=[],
        )
        item_id = item.id

    await run_prune_pass(
        migrated_db, RetentionConfig(max_items=50, max_age_days=7, prune_interval_seconds=300)
    )

    async with migrated_db.session() as session:
        assert await session.get(Item, item_id) is not None
        await ack_item(session, item_id, laptop.id)

    await run_prune_pass(
        migrated_db, RetentionConfig(max_items=50, max_age_days=7, prune_interval_seconds=300)
    )

    async with migrated_db.session() as session:
        assert await session.get(Item, item_id) is None
