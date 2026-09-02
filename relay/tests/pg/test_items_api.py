"""`pg` tests for the item endpoints: create, fetch, catch-up list, ack."""

from __future__ import annotations

from httpx import AsyncClient
from lios_protocol.crypto import generate_group_key, seal

from lios_relay.database.connection import DatabaseConnection
from lios_relay.database.repository import get_device_by_token
from tests.pg.conftest import auth_headers, new_uuid


async def _post_item(
    client: AsyncClient, token: str, blob: bytes, *, target_device_id: str | None = None
) -> dict:
    params = {"target_device_id": target_device_id} if target_device_id else {}
    resp = await client.post(
        "/api/items", content=blob, headers=auth_headers(token), params=params
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


async def test_create_requires_a_bearer_token(client: AsyncClient) -> None:
    resp = await client.post("/api/items", content=b"x" * 16)
    assert resp.status_code in (401, 403)


async def test_create_rejects_empty_body(client: AsyncClient, laptop_token: str) -> None:
    resp = await client.post("/api/items", content=b"", headers=auth_headers(laptop_token))
    assert resp.status_code == 400


async def test_create_rejects_oversized_item(client: AsyncClient, laptop_token: str) -> None:
    oversized = b"x" * (26214400 + 1)
    resp = await client.post("/api/items", content=oversized, headers=auth_headers(laptop_token))
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
        "/api/items", content=b"x" * 8, headers=auth_headers(laptop_token),
        params={"target_device_id": str(new_uuid())},
    )
    assert resp.status_code == 404
