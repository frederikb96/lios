"""Smoke tests for the shared wire models -- construction and JSON round trip."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from lios_protocol.wire import (
    DeviceInfo,
    DevicePaired,
    ItemCreated,
    ItemSummary,
    PairingRedeem,
    PairingSessionCreated,
    PushTokenUpdate,
    StreamEvent,
)


def test_item_summary_round_trips_through_json() -> None:
    item = ItemSummary(
        id=uuid4(),
        sender_device_id=uuid4(),
        target_device_id=None,
        size_bytes=1024,
        created_at=datetime.now(UTC),
    )
    assert ItemSummary.model_validate_json(item.model_dump_json()) == item


def test_stream_event_defaults_type() -> None:
    item = ItemSummary(
        id=uuid4(),
        sender_device_id=uuid4(),
        target_device_id=uuid4(),
        size_bytes=1,
        created_at=datetime.now(UTC),
    )
    event = StreamEvent(item=item)
    assert json.loads(event.model_dump_json())["type"] == "item.new"


def test_device_info_round_trips_through_json() -> None:
    device = DeviceInfo(
        id=uuid4(), display_name="the user's Laptop", platform="linux",
        created_at=datetime.now(UTC), has_push_token=False,
    )
    assert DeviceInfo.model_validate_json(device.model_dump_json()) == device


def test_pairing_redeem_accepts_platform_literal() -> None:
    redeem = PairingRedeem(pairing_code="ABCD1234", platform="ios", display_name="the user's iPhone")
    assert redeem.platform == "ios"


def test_item_created_and_device_paired_and_the_rest_construct() -> None:
    ItemCreated(id=uuid4(), created_at=datetime.now(UTC))
    DevicePaired(device_id=uuid4(), device_token="opaque-token")
    PairingSessionCreated(pairing_code="ABCD1234", expires_at=datetime.now(UTC))
    PushTokenUpdate(apns_token="deadbeef")
