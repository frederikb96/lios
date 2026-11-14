# LIOS

[![CI](https://github.com/frederikberg/lios/actions/workflows/ci.yaml/badge.svg)](https://github.com/frederikberg/lios/actions/workflows/ci.yaml)
[![Release](https://img.shields.io/github/v/release/frederikberg/lios)](https://github.com/frederikberg/lios/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

LIOS (Linux/iOS Sharing) moves text, images and files between an iPhone and a Linux laptop in
both directions, end-to-end encrypted, without the two devices needing to share a local
network.

## How it fits together

```
iPhone                          Relay                            Linux laptop
------                          -----                             ------------
LIOS app                        lios-relay                        LIOS client (resident Flatpak)
  Share Extension  --POST-->      REST API          --WS-->         notify -> open window -> copy
  main app (history)              PostgreSQL                        send: open window -> paste -> POST
  receive path     <--push relay-- push sender
```

Linux can hold an outbound connection open indefinitely, so phone-to-laptop is a genuine
push: the client is already connected, and an item arrives in under a second. iOS cannot hold
a background connection, so laptop-to-phone goes through a push (APNs, via a shared push relay) -- a wake-up signal,
never the transport. The payload is a few kilobytes at most, so the push carries only an item id
and a small sealed preview; the phone fetches the actual (still-encrypted) content over HTTPS.

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
/api/devices/bootstrap`, which is off by default: set `pairing.bootstrap_enabled: true` in
`relay/config-custom/config.override.yaml` (or `LIOS_PAIRING_BOOTSTRAP_ENABLED=true`) while you
pair it, then switch it off again. Every device after that pairs by scanning a QR code an
already-paired device generates. See [`relay/README.md`](relay/README.md) for the full API.

For development -- hot reload, a throwaway Postgres -- see
[`relay/README.md`](relay/README.md#development).

## Installing the Linux client

Every [release](https://github.com/frederikberg/lios/releases) attaches a `.flatpak` bundle
built from the tagged commit.

```bash
flatpak install --user --bundle lios.flatpak
```

It carries a pointer to Flathub's own repo, so a machine with no Flathub remote configured
yet gets offered one automatically to pull `org.gnome.Platform` from. Building the bundle
from source instead is covered in [`linux/README.md`](linux/README.md#packaging).

## Kubernetes

A Helm chart ships in [`charts/lios`](charts/lios) and is published on release:

```bash
helm install lios oci://ghcr.io/frederikberg/charts/lios --version 0.1.0
```

It expects an external PostgreSQL. See the chart's `values.yaml` for the full set of options.

## Configuration

Every option, with its default and an explanation, lives in
[`relay/config/config.yaml`](relay/config/config.yaml). That file is the documentation; this
README does not repeat it.

Configuration comes from that file, then a sparse override file, then environment variables --
and the relay refuses to start on anything missing rather than quietly substituting a
fallback. The one required secret is the database URL. iOS push goes through the shared push
relay with no credential on your side (`push.relay_url`; empty turns push off).

| Variable | Purpose |
|----------|---------|
| `LIOS_DATABASE_URL` | PostgreSQL connection |
| `POSTGRES_PASSWORD` | Database password, used by compose |
| `LIOS_PUSH_RELAY_URL` | Push relay for iOS devices (optional; empty disables push) |
| `LIOS_PAIRING_BOOTSTRAP_ENABLED` | `true` only while pairing the first device of a fresh relay |

## Retention

The relay keeps at most 50 items for 7 days (configurable), pruning earlier once every
intended recipient has acknowledged an item. Each client keeps the same policy in its own
local history -- nothing accumulates server-side, and dismissing a notification is never
destructive.

## Self-hosting for someone other than the author

The relay and its chart are yours to run, and so is push: the relay holds no Apple credential. The
iOS app registers with a shared push relay (compiled into the app) and hands its server only a
ticket, so any relay can push to a phone running the author's build without a key of its own.
The push relay sees the device token and the size and timing of a push, never an item's content.
The iOS app itself is built and signed under one Apple developer account and is not distributed as
an installable artifact for other people; a fork builds its own, with its own bundle id and push
relay.

## Development

Each package documents its own checks: [`protocol/`](protocol/README.md#development),
[`relay/`](relay/README.md#development), [`linux/`](linux/README.md#development) and
[`ios/`](ios/README.md#building-and-testing). Pull requests run them in CI, limited to the
packages a change touches.

```bash
helm lint charts/lios && helm template lios charts/lios      # chart
python scripts/check_release_versions.py                     # version fields agree
```

## License

MIT, see [LICENSE](LICENSE).
