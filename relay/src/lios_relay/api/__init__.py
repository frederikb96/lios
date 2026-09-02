"""API routers, one module per resource: items, devices, the WebSocket stream, and health."""

from __future__ import annotations

from lios_relay.api.devices import router as devices_router
from lios_relay.api.health import router as health_router
from lios_relay.api.items import router as items_router
from lios_relay.api.stream import router as stream_router

all_routers = [items_router, devices_router, stream_router, health_router]

__all__ = ["all_routers"]
