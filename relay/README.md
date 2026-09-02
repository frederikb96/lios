# lios-relay

The LIOS relay: a small FastAPI service that stores sealed item blobs, tracks which paired
device has taken which one, expires everything on a retention policy, and rings an APNs
doorbell when the recipient is an iPhone. It never has the group key and can never read an
item's content -- see [`lios-protocol`](../protocol) for the encryption itself.

## API

All endpoints except `GET /health` and `POST /api/devices/pair` require `Authorization:
Bearer <device_token>`.

| Method | Path | |
|---|---|---|
| POST | `/api/items` | Store a sealed item (raw `application/octet-stream` body). `?target_device_id=` narrows delivery; omitted broadcasts to every other paired device. |
| GET | `/api/items/{id}` | Fetch one item's sealed blob, raw. |
| GET | `/api/items?since=` | Catch-up list of `ItemSummary` (clear metadata only) created after the given timestamp. |
| DELETE | `/api/items/{id}` | A device acknowledging it has taken an item. |
| GET | `/api/stream` | WebSocket; announces each new item as it arrives. See `lios_relay.api.stream`'s module docstring for the reconnect contract. |
| POST | `/api/devices/pairing-sessions` | An already-paired device mints a fresh pairing code. |
| POST | `/api/devices/pair` | Redeem a pairing code for a device token -- the one endpoint that needs no token. |
| POST | `/api/devices/{id}/push-token` | Register an APNs token for the caller's own device. |
| GET | `/health` | For the Kubernetes probes. |

Every request/response shape is a `lios_protocol.wire` Pydantic model, shared with every
client so the contract cannot drift.

## Configuration

Every option, with its default and an explanation, lives in
[`config/config.yaml`](config/config.yaml). Config loads from that file, then a sparse
`config-custom/config.override.yaml`, then `LIOS_<SECTION>_<KEY>` environment variables --
and the service refuses to start on anything missing rather than silently falling back.

Push (`apns.*`) is the one section that may be entirely empty: the relay starts and serves
every other endpoint fine with no APNs key configured, simply sending no push.

## Development

```bash
cd relay
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
ruff check .
mypy src/
pytest -m unit
pytest -m pg      # needs a container runtime (podman) for testcontainers
```

Bring up the full stack (relay + Postgres) locally:

```bash
cp ../.dev.env.example ../.dev.env   # fill in values
podman compose --env-file ../.dev.env -f ../compose.dev.yaml up -d
curl http://localhost:18090/health
```

See the repository root [README](../README.md) for the compose files and the Helm chart.
