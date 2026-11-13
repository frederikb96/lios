"""Unit tests for the push client, against an in-process stand-in for the push relay."""

from __future__ import annotations

import base64
import json
import uuid

import httpx
import pytest
from lios_protocol.headers import PUSH_RELAY_APP

from lios_relay.config import PushConfig
from lios_relay.push import PushTarget, PushUnavailable, send_new_item_push

CONFIG = PushConfig(relay_url="https://push.example.test/", send_timeout_seconds=5, ttl_seconds=0)
ITEM_ID = uuid.uuid4()
SENDER_ID = uuid.uuid4()
TARGET = PushTarget(device_id=uuid.uuid4(), ticket="ticket-1")


async def _send(
    handler, *, targets: list[PushTarget] | None = None, sealed_preview: bytes | None = b"p"
) -> list[uuid.UUID]:
    return await send_new_item_push(
        config=CONFIG,
        targets=[TARGET] if targets is None else targets,
        item_id=ITEM_ID,
        sender_device_id=SENDER_ID,
        sealed_preview=sealed_preview,
        transport=httpx.MockTransport(handler),
    )


def _blob_fields(request: httpx.Request) -> dict:
    return json.loads(base64.b64decode(json.loads(request.content)["blob"]))


async def test_posts_the_ticket_and_blob_to_the_push_relay() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202, json={"apns_id": "x"})

    assert await _send(handler) == []

    assert len(seen) == 1
    assert str(seen[0].url) == "https://push.example.test/v1/push"
    body = json.loads(seen[0].content)
    assert (body["app"], body["ticket"], body["type"]) == (PUSH_RELAY_APP, "ticket-1", "alert")
    assert body["ttl_seconds"] == 0
    assert _blob_fields(seen[0]) == {
        "item_id": str(ITEM_ID),
        "sender_device_id": str(SENDER_ID),
        "sealed_preview": base64.b64encode(b"p").decode(),
    }


@pytest.mark.parametrize("status", [401, 410])
async def test_a_ticket_the_relay_rejects_for_good_is_reported(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"reason": "x"})

    assert await _send(handler) == [TARGET.device_id]


@pytest.mark.parametrize("status", [429, 502])
async def test_a_transient_failure_keeps_the_ticket(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    assert await _send(handler) == []


async def test_an_unreachable_relay_keeps_the_ticket() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    assert await _send(handler) == []


async def test_an_oversized_blob_is_retried_without_the_preview() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(413 if len(seen) == 1 else 202)

    assert await _send(handler) == []

    assert len(seen) == 2
    assert "sealed_preview" in _blob_fields(seen[0])
    assert "sealed_preview" not in _blob_fields(seen[1])


async def test_a_dead_ticket_is_reported_per_device() -> None:
    other = PushTarget(device_id=uuid.uuid4(), ticket="ticket-2")

    def handler(request: httpx.Request) -> httpx.Response:
        dead = json.loads(request.content)["ticket"] == "ticket-2"
        return httpx.Response(410 if dead else 202)

    assert await _send(handler, targets=[TARGET, other]) == [other.device_id]


async def test_nothing_is_sent_without_a_relay_or_a_ticket() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    with pytest.raises(PushUnavailable):
        await _send(handler, targets=[])
    with pytest.raises(PushUnavailable):
        await send_new_item_push(
            config=PushConfig(relay_url="", send_timeout_seconds=5, ttl_seconds=0),
            targets=[TARGET], item_id=ITEM_ID, sender_device_id=SENDER_ID,
            sealed_preview=None, transport=httpx.MockTransport(handler),
        )
