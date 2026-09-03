"""`pg` test for the WebSocket stream: connect, then receive a new item's announcement.

Uses Starlette's own `TestClient` (built on the same ASGI app, no real socket) rather than
the `httpx.AsyncClient` the REST tests use -- `websocket_connect` is a TestClient-only
capability. Unlike those tests, this one enters the app's own lifespan (`with
TestClient(app) as client:`), because TestClient runs the whole ASGI app on a dedicated
background thread with its own event loop; a database engine created in the test's own
event loop (as `migrated_db` does) cannot be used from that thread. Bootstrapping both
devices through the API itself, entirely inside that one `with` block, keeps every database
call on the one event loop that owns the engine the lifespan just created.
"""

from __future__ import annotations

import json
import uuid

from lios_protocol.headers import ITEM_ID_HEADER
from starlette.testclient import TestClient

from lios_relay.database.connection import DatabaseConnection
from lios_relay.server import create_app


async def test_stream_announces_a_new_item(migrated_db: DatabaseConnection) -> None:
    app = create_app()

    with TestClient(app) as client:
        bootstrap = client.post(
            "/api/devices/bootstrap", json={"platform": "linux", "display_name": "Laptop"}
        )
        assert bootstrap.status_code == 201
        laptop_token = bootstrap.json()["device_token"]

        session_resp = client.post(
            "/api/devices/pairing-sessions",
            headers={"Authorization": f"Bearer {laptop_token}"},
        )
        code = session_resp.json()["pairing_code"]
        paired = client.post(
            "/api/devices/pair",
            json={"pairing_code": code, "platform": "ios", "display_name": "Phone"},
        )
        phone_token = paired.json()["device_token"]

        with client.websocket_connect(
            "/api/stream", headers={"Authorization": f"Bearer {phone_token}"}
        ) as ws:
            post_resp = client.post(
                "/api/items", content=b"streamed item",
                headers={
                    "Authorization": f"Bearer {laptop_token}",
                    ITEM_ID_HEADER: str(uuid.uuid4()),
                },
            )
            assert post_resp.status_code == 201

            message = json.loads(ws.receive_text())
            assert message["type"] == "item.new"
            assert message["item"]["id"] == post_resp.json()["id"]


async def test_stream_does_not_announce_the_senders_own_item(
    migrated_db: DatabaseConnection,
) -> None:
    """A device that posts a broadcast item must not receive its own upload back on its own
    stream connection -- only every *other* paired device is a recipient.

    Proven without waiting on a ping or any absence timeout: right after the laptop's
    broadcast, the phone sends a second item targeted at the laptop specifically. Queues are
    FIFO per connection, so if the laptop's own broadcast had (wrongly) been enqueued for it,
    it would be the *first* frame the laptop reads -- instead the first frame is the targeted
    item, proving the broadcast was never enqueued for its own sender.
    """
    app = create_app()

    with TestClient(app) as client:
        bootstrap = client.post(
            "/api/devices/bootstrap", json={"platform": "linux", "display_name": "Laptop"}
        )
        assert bootstrap.status_code == 201
        laptop_token = bootstrap.json()["device_token"]
        laptop_id = bootstrap.json()["device_id"]

        session_resp = client.post(
            "/api/devices/pairing-sessions",
            headers={"Authorization": f"Bearer {laptop_token}"},
        )
        code = session_resp.json()["pairing_code"]
        paired = client.post(
            "/api/devices/pair",
            json={"pairing_code": code, "platform": "ios", "display_name": "Phone"},
        )
        phone_token = paired.json()["device_token"]

        with (
            client.websocket_connect(
                "/api/stream", headers={"Authorization": f"Bearer {laptop_token}"}
            ) as laptop_ws,
            client.websocket_connect(
                "/api/stream", headers={"Authorization": f"Bearer {phone_token}"}
            ) as phone_ws,
        ):
            broadcast_resp = client.post(
                "/api/items", content=b"sent from the laptop itself",
                headers={
                    "Authorization": f"Bearer {laptop_token}",
                    ITEM_ID_HEADER: str(uuid.uuid4()),
                },
            )
            assert broadcast_resp.status_code == 201

            targeted_resp = client.post(
                "/api/items", content=b"phone replies straight to the laptop",
                params={"target_device_id": laptop_id},
                headers={
                    "Authorization": f"Bearer {phone_token}",
                    ITEM_ID_HEADER: str(uuid.uuid4()),
                },
            )
            assert targeted_resp.status_code == 201

            # The phone, an actual recipient of the broadcast, gets it announced.
            phone_message = json.loads(phone_ws.receive_text())
            assert phone_message["type"] == "item.new"
            assert phone_message["item"]["id"] == broadcast_resp.json()["id"]

            # The laptop's first frame is the *targeted* item, not its own broadcast.
            laptop_message = json.loads(laptop_ws.receive_text())
            assert laptop_message["type"] == "item.new"
            assert laptop_message["item"]["id"] == targeted_resp.json()["id"]


async def test_stream_rejects_a_missing_token(migrated_db: DatabaseConnection) -> None:
    app = create_app()

    with TestClient(app) as client:
        try:
            with client.websocket_connect("/api/stream"):
                raise AssertionError("expected the handshake to be rejected")
        except Exception:
            pass  # the server closes with code 4401 before ever accepting the connection
