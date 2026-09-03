"""HTTP header, query param and APNs payload field names for the parts of the relay's item
contract that are not JSON -- the sealed blob itself, and the small pieces of metadata that
ride alongside it outside a JSON body (to keep a large item off base64 entirely).

Shared here so the relay and every client that talks to it directly agree on the exact
strings without re-deriving them per language -- a Swift mirror of these same constants lives
in `LIOSKit`'s `RelayClient.Header` and `PushPayload`.
"""

from __future__ import annotations

#: `POST /api/items` request headers. `target_device_id` is a query param instead (see
#: below) -- it is a plain filter unrelated to the sealed blob, and a query param is the more
#: conventional place for one.
ITEM_ID_HEADER = "X-Item-Id"
SEALED_PREVIEW_HEADER = "X-Sealed-Preview"

#: `POST /api/items` query param narrowing delivery to one device.
TARGET_DEVICE_ID_QUERY_PARAM = "target_device_id"

#: `GET /api/items` query param switching the catch-up list from items the caller received
#: to items the caller itself sent -- a device is never its own recipient, so this is a
#: separate query rather than a wider version of the default one.
SENT_QUERY_PARAM = "sent"

#: Custom (non-`aps`) fields on the APNs payload `lios_relay.push` sends.
PUSH_ITEM_ID_KEY = "item_id"
PUSH_SENDER_DEVICE_ID_KEY = "sender_device_id"
PUSH_SEALED_PREVIEW_KEY = "sealed_preview"
