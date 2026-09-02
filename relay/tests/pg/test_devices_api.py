"""`pg` tests for pairing and the device registry."""

from __future__ import annotations

from httpx import AsyncClient

from tests.pg.conftest import auth_headers


async def test_bootstrap_registers_the_first_device(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/devices/bootstrap", json={"platform": "linux", "display_name": "First Laptop"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "device_id" in body and "device_token" in body

    listed = await client.get("/api/items", headers=auth_headers(body["device_token"]))
    assert listed.status_code == 200


async def test_bootstrap_refuses_once_a_device_exists(
    client: AsyncClient, laptop_token: str
) -> None:
    resp = await client.post(
        "/api/devices/bootstrap", json={"platform": "linux", "display_name": "Second Laptop"}
    )
    assert resp.status_code == 403


async def test_pairing_session_requires_an_existing_device(client: AsyncClient) -> None:
    resp = await client.post("/api/devices/pairing-sessions")
    assert resp.status_code in (401, 403)


async def test_full_pairing_flow(client: AsyncClient, laptop_token: str) -> None:
    session_resp = await client.post(
        "/api/devices/pairing-sessions", headers=auth_headers(laptop_token)
    )
    assert session_resp.status_code == 201
    code = session_resp.json()["pairing_code"]

    pair_resp = await client.post(
        "/api/devices/pair",
        json={"pairing_code": code, "platform": "ios", "display_name": "New iPhone"},
    )
    assert pair_resp.status_code == 201
    body = pair_resp.json()
    assert "device_id" in body and "device_token" in body

    # The new token is immediately usable against an authenticated endpoint.
    listed = await client.get("/api/items", headers=auth_headers(body["device_token"]))
    assert listed.status_code == 200


async def test_pairing_code_is_single_use(client: AsyncClient, laptop_token: str) -> None:
    session_resp = await client.post(
        "/api/devices/pairing-sessions", headers=auth_headers(laptop_token)
    )
    code = session_resp.json()["pairing_code"]

    body = {"pairing_code": code, "platform": "linux", "display_name": "Second Laptop"}
    first = await client.post("/api/devices/pair", json=body)
    second = await client.post("/api/devices/pair", json=body)

    assert first.status_code == 201
    assert second.status_code == 401


async def test_pairing_rejects_unknown_code(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/devices/pair",
        json={"pairing_code": "NOTREAL1", "platform": "linux", "display_name": "Nobody"},
    )
    assert resp.status_code == 401


async def test_set_push_token_for_own_device(client: AsyncClient, phone_token: str) -> None:
    """A device that paired through the API can register a push token for itself."""
    session_resp = await client.post(
        "/api/devices/pairing-sessions", headers=auth_headers(phone_token)
    )
    code = session_resp.json()["pairing_code"]
    paired = await client.post(
        "/api/devices/pair",
        json={"pairing_code": code, "platform": "ios", "display_name": "Second Phone"},
    )
    device_id, token = paired.json()["device_id"], paired.json()["device_token"]

    resp = await client.post(
        f"/api/devices/{device_id}/push-token",
        json={"apns_token": "deadbeef"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 204


async def test_cannot_set_push_token_for_a_different_device(
    client: AsyncClient, laptop_token: str, phone_token: str
) -> None:
    session_resp = await client.post(
        "/api/devices/pairing-sessions", headers=auth_headers(laptop_token)
    )
    code = session_resp.json()["pairing_code"]
    paired = await client.post(
        "/api/devices/pair",
        json={"pairing_code": code, "platform": "ios", "display_name": "Another Phone"},
    )
    other_device_id = paired.json()["device_id"]

    resp = await client.post(
        f"/api/devices/{other_device_id}/push-token",
        json={"apns_token": "deadbeef"},
        headers=auth_headers(phone_token),
    )
    assert resp.status_code == 403
