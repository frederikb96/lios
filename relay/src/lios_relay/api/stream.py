"""`GET /api/stream` -- the long-lived WebSocket connection the Linux client holds,
announcing new items as they arrive.

## Reconnect contract

The stream only ever announces items created *after* the socket connected -- it is a live
doorbell, not a durable replay channel. A client must:

- On every connect (including the first), remember the current time, then follow up with
  `GET /api/items?since=<that time>` to catch up on anything created in the gap between a
  previous disconnect and this connect (or, on first connect ever, everything within
  retention).
- On disconnect (a network change, the relay restarting, anything), reconnect with
  exponential backoff -- 1s, 2s, 4s, ... capped at 60s, with jitter -- and repeat the catch-up
  step above. Treat a server-initiated close identically to a network error: never a signal
  to stop reconnecting.
- Expect a text ping frame roughly every 30 seconds while otherwise idle, and treat the
  absence of any frame (ping or event) for significantly longer than that as a dead
  connection worth closing and reconnecting, rather than trusting the TCP-level keepalive.

Authentication is the same bearer device token as every other endpoint, sent as the
`Authorization` header on the WebSocket handshake -- every client here is a native
application in full control of its own handshake, not a browser page restricted to the
`WebSocket` constructor's fixed header set.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from lios_relay.database.connection import get_db_connection
from lios_relay.database.repository import get_device_by_token
from lios_relay.server_state import get_broadcaster

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stream"])

#: How often a ping is sent to an otherwise-idle connection -- see the reconnect contract
#: above, which a client relies on to detect a connection that died without a close frame.
_PING_INTERVAL_SECONDS = 30.0


@router.websocket("/api/stream")
async def stream(websocket: WebSocket) -> None:
    """Authenticate, then forward every published item event until the client disconnects."""
    auth_header = websocket.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        await websocket.close(code=4401, reason="missing bearer token")
        return

    async with get_db_connection().session() as session:
        device = await get_device_by_token(session, token)
    if device is None:
        await websocket.close(code=4401, reason="invalid device token")
        return

    await websocket.accept()
    broadcaster = get_broadcaster()
    queue = broadcaster.subscribe(device.id)
    try:
        while True:
            try:
                event_json = await asyncio.wait_for(queue.get(), timeout=_PING_INTERVAL_SECONDS)
            except TimeoutError:
                if websocket.application_state != WebSocketState.CONNECTED:
                    break
                await websocket.send_text('{"type":"ping"}')
                continue
            await websocket.send_text(event_json)
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.unsubscribe(queue)
