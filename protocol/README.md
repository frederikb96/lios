# lios-protocol

Shared crypto, framing, pairing and wire types for the LIOS relay and its clients. Free of any
web-framework or GTK/UIKit import, so it is a plain library dependency everywhere it is used.

## What lives here

- `lios_protocol.crypto` — AES-256-GCM sealing of one opaque blob under the shared group key.
- `lios_protocol.framing` — packing an item's metadata and payload into one buffer before it is
  sealed, and unpacking it after it is opened.
- `lios_protocol.pairing` — building and reading the QR payload that carries the group key from
  an already-paired device to a new one. The group key never touches the relay; it exists only
  inside this payload and in each device's own local key storage.
- `lios_protocol.wire` — the Pydantic request/response models the relay and every client share,
  so they cannot drift apart on what an API call contains.

## Using it from another package in this repository

This package is not part of a workspace — each consumer (`relay/`, and eventually `linux/`) adds
it as an editable local path dependency in its own `pyproject.toml`:

```toml
dependencies = ["lios-protocol"]

[tool.uv.sources]
lios-protocol = { path = "../protocol", editable = true }
```

## Development

```bash
cd protocol
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
ruff check .
mypy src/
pytest
```
