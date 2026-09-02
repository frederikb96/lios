# LIOS

[![CI](https://github.com/frederikb96/lios/actions/workflows/ci.yaml/badge.svg)](https://github.com/frederikb96/lios/actions/workflows/ci.yaml)
[![Release](https://img.shields.io/github/v/release/frederikb96/lios)](https://github.com/frederikb96/lios/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

LIOS (Linux/iOS Sharing) moves text, images and files between an iPhone and a Linux laptop in
both directions, end-to-end encrypted, without the two devices needing to share a local
network.

## How it fits together

```
iPhone                          Relay                            Linux laptop
------                          -----                             ------------
LIOS app                        lios-relay                        LIOS client (systemd --user)
  Share Extension  --POST-->      REST API          --WS-->         receive -> clipboard + notify
  main app (history)              PostgreSQL                        send: shortcut -> clipboard -> POST
  receive path     <--APNs--       APNs sender
```

Linux can hold an outbound connection open indefinitely, so phone-to-laptop is a genuine
push: the client is already connected, and an item arrives in under a second. iOS cannot hold
a background connection, so laptop-to-phone goes through APNs -- a wake-up signal, never the
transport. An APNs payload is a few kilobytes at most, so the push carries only an item id;
the phone fetches the actual (still-encrypted) content over HTTPS.

A shared symmetric AES-256-GCM key, established once at pairing and carried only inside a QR
code, encrypts every item end to end. The relay stores and forwards ciphertext it can never
open -- see [`protocol/`](protocol) for the crypto, and [`relay/`](relay) for the service that
uses it. [`linux/`](linux) and [`ios/`](ios) hold the two clients.

## Running the relay

Both compose files bring up the relay and PostgreSQL together.

```bash
cp .prod.env.example .prod.env      # fill in the secrets below
podman compose --env-file .prod.env up -d
```

The relay is then on <http://localhost:8080>. Pair your first device against `POST
/api/devices/bootstrap`; every device after that pairs by scanning a QR code an
already-paired device generates. See [`relay/README.md`](relay/README.md) for the full API.

For development -- hot reload, a throwaway Postgres -- see
[`relay/README.md`](relay/README.md#development).

## Kubernetes

A Helm chart ships in [`charts/lios`](charts/lios) and is published on release:

```bash
helm install lios oci://ghcr.io/frederikb96/charts/lios --version 0.1.0
```

It expects an external PostgreSQL. See the chart's `values.yaml` for the full set of options.

## Configuration

Every option, with its default and an explanation, lives in
[`relay/config/config.yaml`](relay/config/config.yaml). That file is the documentation; this
README does not repeat it.

Configuration comes from that file, then a sparse override file, then environment variables --
and the relay refuses to start on anything missing rather than quietly substituting a
fallback. The one required secret is the database URL; APNs push is entirely optional and the
relay works fine with none of it configured.

| Variable | Purpose |
|----------|---------|
| `LIOS_DATABASE_URL` | PostgreSQL connection |
| `POSTGRES_PASSWORD` | Database password, used by compose |
| `LIOS_APNS_KEY_ID` / `LIOS_APNS_TEAM_ID` / `LIOS_APNS_AUTH_KEY_B64` | APNs push credentials (optional) |

## Retention

The relay keeps at most 50 items for 7 days (configurable), pruning earlier once every
intended recipient has acknowledged an item. Each client keeps the same policy in its own
local history -- nothing accumulates server-side, and dismissing a notification is never
destructive.

## Self-hosting for someone other than the author

The relay and its chart are yours to run. The iOS app, though, is built and signed under one
Apple developer account and can only ever send push through that account's own APNs
credentials -- there is no shared third-party relay in the middle the way some public push
services work. Running your own LIOS therefore means your own Apple developer account and
your own TestFlight build alongside your own relay; the iOS app in this repository is not
distributed as an installable artifact for other people's relays.

## License

MIT, see [LICENSE](LICENSE).
