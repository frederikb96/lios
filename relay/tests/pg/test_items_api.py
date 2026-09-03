"""`pg` tests for the item endpoints: create, fetch, catch-up list, ack."""

from __future__ import annotations

import base64
import uuid

import pytest
from httpx import AsyncClient
from lios_protocol.crypto import generate_group_key, seal
from lios_protocol.headers import (
    ITEM_ID_HEADER,
    SEALED_PREVIEW_HEADER,
    SENT_QUERY_PARAM,
    TARGET_DEVICE_ID_QUERY_PARAM,
)

import lios_relay.api.items as items_module
from lios_relay.database.connection import DatabaseConnection
from lios_relay.database.models import Item
from lios_relay.database.repository import create_device, generate_device_token, get_device_by_token
from tests.pg.conftest import auth_headers, new_uuid


def _item_headers(
    token: str, *, item_id: uuid.UUID | None = None, sealed_preview: bytes | None = None,
) -> dict[str, str]:
    """Auth plus the item-creation headers -- `X-Item-Id` always present, since the client
    always generates its own before ever sealing a blob. `target_device_id` is a query param,
    not a header -- see `_post_item`."""
    headers = dict(auth_headers(token))
    headers[ITEM_ID_HEADER] = str(item_id or new_uuid())
    if sealed_preview:
        headers[SEALED_PREVIEW_HEADER] = base64.b64encode(sealed_preview).decode("ascii")
    return headers


async def _post_item(
    client: AsyncClient,
    token: str,
    blob: bytes,
    *,
    item_id: uuid.UUID | None = None,
    target_device_id: str | None = None,
    sealed_preview: bytes | None = None,
) -> dict:
    params = {TARGET_DEVICE_ID_QUERY_PARAM: target_device_id} if target_device_id else {}
    resp = await client.post(
        "/api/items", content=blob, params=params,
        headers=_item_headers(token, item_id=item_id, sealed_preview=sealed_preview),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_and_fetch_item_round_trips_the_sealed_blob(
    client: AsyncClient, laptop_token: str, phone_token: str,
) -> None:
    key = generate_group_key()
    blob = seal(key, b"hello from the laptop")

    created = await _post_item(client, laptop_token, blob)
    assert "id" in created and "created_at" in created

    fetched = await client.get(f"/api/items/{created['id']}", headers=auth_headers(phone_token))
    assert fetched.status_code == 200
    assert fetched.content == blob


async def test_item_is_committed_before_it_is_announced_or_pushed(
    client: AsyncClient,
    laptop_token: str,
    phone_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stream event and the push both go out only once the item is durably visible to a
    different connection -- never from inside the still-open transaction that created it.

    Hooks the recipient push step, which the endpoint only reaches after it has already
    published the stream event, and fetches the item there on its own fresh session -- exactly
    what a recipient reacting to either signal does. No timing dependency: the hook runs
    in the request's own control flow, strictly between the announcement and the eventual
    commit, so this either fails every time the ordering is wrong or passes every time it
    is right.
    """
    item_id = new_uuid()
    probe_response = {}
    original_push = items_module._push_to_recipients

    async def probing_push(*args, **kwargs):
        probe_response["get"] = await client.get(
            f"/api/items/{item_id}", headers=auth_headers(phone_token)
        )
        return await original_push(*args, **kwargs)

    monkeypatch.setattr(items_module, "_push_to_recipients", probing_push)

    created = await _post_item(client, laptop_token, b"probe me", item_id=item_id)
    assert created["id"] == str(item_id)

    assert "get" in probe_response, "expected the push step to run"
    assert probe_response["get"].status_code == 200, (
        "item was not yet committed when its announcement/push step ran"
    )


async def test_created_item_id_is_the_clients_own(client: AsyncClient, laptop_token: str) -> None:
    item_id = new_uuid()
    created = await _post_item(client, laptop_token, b"client picks the id", item_id=item_id)
    assert created["id"] == str(item_id)


async def test_create_requires_an_item_id_header(client: AsyncClient, laptop_token: str) -> None:
    resp = await client.post("/api/items", content=b"x" * 8, headers=auth_headers(laptop_token))
    assert resp.status_code == 422


async def test_create_rejects_a_malformed_item_id(client: AsyncClient, laptop_token: str) -> None:
    headers = dict(auth_headers(laptop_token))
    headers[ITEM_ID_HEADER] = "not-a-uuid"
    resp = await client.post("/api/items", content=b"x" * 8, headers=headers)
    assert resp.status_code == 400


async def test_create_rejects_a_reused_item_id(client: AsyncClient, laptop_token: str) -> None:
    item_id = new_uuid()
    first = await _post_item(client, laptop_token, b"first use of this id", item_id=item_id)
    assert first["id"] == str(item_id)

    resp = await client.post(
        "/api/items", content=b"second use, same id",
        headers=_item_headers(laptop_token, item_id=item_id),
    )
    assert resp.status_code == 409


async def test_create_accepts_a_sealed_preview(
    client: AsyncClient, laptop_token: str, migrated_db: DatabaseConnection,
) -> None:
    item_id = new_uuid()
    preview = b"sealed-preview-bytes"
    created = await _post_item(
        client, laptop_token, b"payload with a preview", item_id=item_id, sealed_preview=preview,
    )

    async with migrated_db.session() as session:
        stored = await session.get(Item, uuid.UUID(created["id"]))
    assert stored is not None
    assert stored.sealed_preview == preview


async def test_create_rejects_invalid_base64_preview(
    client: AsyncClient, laptop_token: str
) -> None:
    headers = dict(auth_headers(laptop_token))
    headers[ITEM_ID_HEADER] = str(new_uuid())
    headers[SEALED_PREVIEW_HEADER] = "not valid base64!!"
    resp = await client.post("/api/items", content=b"x" * 8, headers=headers)
    assert resp.status_code == 400


async def test_create_requires_a_bearer_token(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/items", content=b"x" * 16, headers={ITEM_ID_HEADER: str(new_uuid())},
    )
    assert resp.status_code in (401, 403)


async def test_create_rejects_empty_body(client: AsyncClient, laptop_token: str) -> None:
    resp = await client.post("/api/items", content=b"", headers=_item_headers(laptop_token))
    assert resp.status_code == 400


async def test_create_rejects_oversized_item(client: AsyncClient, laptop_token: str) -> None:
    oversized = b"x" * (26214400 + 1)
    resp = await client.post(
        "/api/items", content=oversized, headers=_item_headers(laptop_token)
    )
    assert resp.status_code == 413


async def test_broadcast_item_is_visible_to_every_other_device(
    client: AsyncClient, laptop_token: str, phone_token: str,
) -> None:
    created = await _post_item(client, laptop_token, b"broadcast payload")

    listed = await client.get("/api/items", headers=auth_headers(phone_token))
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()]
    assert created["id"] in ids

    item = next(item for item in listed.json() if item["id"] == created["id"])
    assert item["target_device_id"] is None


async def test_since_filters_out_earlier_items(client: AsyncClient, laptop_token: str) -> None:
    first = await _post_item(client, laptop_token, b"first item")

    listed = await client.get(
        "/api/items", headers=auth_headers(laptop_token), params={"since": first["created_at"]},
    )
    ids = [item["id"] for item in listed.json()]
    assert first["id"] not in ids


async def test_catch_up_list_never_includes_the_senders_own_broadcast(
    client: AsyncClient, laptop_token: str, phone_token: str,
) -> None:
    """A sender is never its own recipient, so its own broadcast must not reappear through
    catch-up either -- not just be missing from the live stream."""
    created = await _post_item(client, laptop_token, b"broadcast payload")

    listed = await client.get("/api/items", headers=auth_headers(laptop_token))
    ids = [item["id"] for item in listed.json()]
    assert created["id"] not in ids

    # Confirm it isn't just filtered by "since" -- the recipient (phone) still sees it.
    listed_by_phone = await client.get("/api/items", headers=auth_headers(phone_token))
    assert created["id"] in [item["id"] for item in listed_by_phone.json()]


async def test_sent_query_returns_what_the_device_itself_sent(
    client: AsyncClient, laptop_token: str, phone_token: str,
) -> None:
    """`sent=true` is a separate query, not a widening of the default one -- the default
    list keeps excluding the sender's own item exactly as before."""
    created = await _post_item(client, laptop_token, b"my own upload")

    sent_by_laptop = await client.get(
        "/api/items", headers=auth_headers(laptop_token), params={SENT_QUERY_PARAM: "true"},
    )
    assert sent_by_laptop.status_code == 200
    assert created["id"] in [item["id"] for item in sent_by_laptop.json()]

    default_for_laptop = await client.get("/api/items", headers=auth_headers(laptop_token))
    assert created["id"] not in [item["id"] for item in default_for_laptop.json()]

    sent_by_phone = await client.get(
        "/api/items", headers=auth_headers(phone_token), params={SENT_QUERY_PARAM: "true"},
    )
    assert created["id"] not in [item["id"] for item in sent_by_phone.json()]


async def test_sent_query_respects_since(client: AsyncClient, laptop_token: str) -> None:
    first = await _post_item(client, laptop_token, b"first sent item")

    listed = await client.get(
        "/api/items", headers=auth_headers(laptop_token),
        params={SENT_QUERY_PARAM: "true", "since": first["created_at"]},
    )
    assert first["id"] not in [item["id"] for item in listed.json()]


async def test_a_sender_can_ack_its_own_item(
    client: AsyncClient, laptop_token: str,
) -> None:
    """The ack endpoint accepts any authenticated device, sender included -- what lets a
    device that lists its own sent items also drop them once recorded locally."""
    created = await _post_item(client, laptop_token, b"ack my own upload")
    resp = await client.delete(
        f"/api/items/{created['id']}", headers=auth_headers(laptop_token)
    )
    assert resp.status_code == 204


async def test_catch_up_list_only_reaches_the_targeted_device(
    client: AsyncClient, laptop_token: str, phone_token: str, migrated_db: DatabaseConnection,
) -> None:
    """A targeted item must not show up in a bystander's catch-up list -- only the one device
    it was addressed to, and never the sender."""
    async with migrated_db.session() as session:
        phone = await get_device_by_token(session, phone_token)
    assert phone is not None

    third_token = generate_device_token()
    async with migrated_db.session() as session:
        await create_device(
            session, display_name="Test Tablet", platform="linux", token=third_token
        )

    created = await _post_item(
        client, laptop_token, b"just for you", target_device_id=str(phone.id)
    )

    listed_by_target = await client.get("/api/items", headers=auth_headers(phone_token))
    assert created["id"] in [item["id"] for item in listed_by_target.json()]

    listed_by_bystander = await client.get("/api/items", headers=auth_headers(third_token))
    assert created["id"] not in [item["id"] for item in listed_by_bystander.json()]

    listed_by_sender = await client.get("/api/items", headers=auth_headers(laptop_token))
    assert created["id"] not in [item["id"] for item in listed_by_sender.json()]


async def test_get_unknown_item_is_404(client: AsyncClient, laptop_token: str) -> None:
    resp = await client.get(f"/api/items/{new_uuid()}", headers=auth_headers(laptop_token))
    assert resp.status_code == 404


async def test_ack_unknown_item_is_a_no_op_not_an_error(
    client: AsyncClient, laptop_token: str
) -> None:
    resp = await client.delete(f"/api/items/{new_uuid()}", headers=auth_headers(laptop_token))
    assert resp.status_code == 204


async def test_ack_is_idempotent(
    client: AsyncClient, laptop_token: str, phone_token: str
) -> None:
    created = await _post_item(client, laptop_token, b"ack me twice")
    first = await client.delete(f"/api/items/{created['id']}", headers=auth_headers(phone_token))
    second = await client.delete(f"/api/items/{created['id']}", headers=auth_headers(phone_token))
    assert first.status_code == 204
    assert second.status_code == 204


async def test_targeted_item_records_the_target(
    client: AsyncClient, laptop_token: str, phone_token: str, migrated_db: DatabaseConnection,
) -> None:
    async with migrated_db.session() as session:
        phone = await get_device_by_token(session, phone_token)
    assert phone is not None

    created = await _post_item(
        client, laptop_token, b"just for you", target_device_id=str(phone.id)
    )

    listed = await client.get("/api/items", headers=auth_headers(phone_token))
    item = next(item for item in listed.json() if item["id"] == created["id"])
    assert item["target_device_id"] == str(phone.id)


async def test_targeted_item_rejects_unknown_target(
    client: AsyncClient, laptop_token: str
) -> None:
    resp = await client.post(
        "/api/items", content=b"x" * 8,
        params={TARGET_DEVICE_ID_QUERY_PARAM: str(new_uuid())},
        headers=_item_headers(laptop_token),
    )
    assert resp.status_code == 404
