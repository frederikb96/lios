"""HTTP header and APNs payload field names for the parts of the relay's item contract that
are not JSON -- the sealed blob itself, and the small pieces of metadata that ride alongside
it as headers rather than inside a JSON body (to keep a large item off base64 entirely).

Shared here so the relay and every client that talks to it directly agree on the exact
strings without re-deriving them per language -- a Swift mirror of these same constants lives
in `LIOSKit`'s `RelayClient.Header` and `PushPayload`.
"""

from __future__ import annotations

#: `POST /api/items` request headers.
ITEM_ID_HEADER = "X-Item-Id"
TARGET_DEVICE_ID_HEADER = "X-Target-Device-Id"
SEALED_PREVIEW_HEADER = "X-Sealed-Preview"

#: Custom (non-`aps`) fields on the APNs payload `lios_relay.push` sends.
PUSH_ITEM_ID_KEY = "item_id"
PUSH_SENDER_DEVICE_ID_KEY = "sender_device_id"
PUSH_SEALED_PREVIEW_KEY = "sealed_preview"
