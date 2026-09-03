# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- `lios-linux` is now a resident application with no separate helper process: it stays
  running under GNOME's Background Apps with no window open, and closing its window hides it
  rather than exiting. Sending is a paste into the window (text, an image, or a file, from
  whatever the clipboard or a drop offers); receiving is a notification whose click opens the
  window with the new item selected, ready to copy or save with a button or its accelerator.
- Removed the `wl-copy`/`wl-paste` clipboard backend, the subprocess plumbing under it, and
  the GlobalShortcuts portal registration -- every clipboard touch now goes through native
  `Gdk.Clipboard` from inside a focused window, so the Flatpak bundles no GPL binary.
- `lios send-clipboard` and `lios send-file` are gone; `lios show` (or no subcommand) is the
  one command-line entry point any desktop's own keyboard settings can bind.

### Fixed

- The Linux client's relay stream handler converted every incoming WebSocket frame with
  `bytes(...)` on a `GLib.Bytes` object, which always raised -- nothing sent from the phone
  ever reached the laptop, and the failure repeated on every keepalive too.

## [0.1.1] - 2026-09-02

### Fixed

- `POST /api/items` reads `target_device_id` as a query parameter rather than a header,
  matching both clients. A targeted send against 0.1.0 was silently broadcast to every
  paired device instead of the one named.

## [0.1.0] - 2026-09-02

### Added

- `lios-protocol`: shared AES-256-GCM sealing, metadata/payload framing, QR-based device
  pairing, and the Pydantic wire types the relay and every client build against.
- `lios-relay`: a FastAPI service storing sealed items, tracking per-device acknowledgements
  against a per-item recipient snapshot, pruning on a configurable retention policy, and
  pushing a generic APNs notification when a recipient is an iOS device with a registered
  token. WebSocket stream for live delivery, bearer device-token auth throughout, a
  first-device bootstrap endpoint, Postgres via SQLAlchemy async + Alembic. Item ids are
  client-generated (the sealed blob's own associated data binds the id, so the relay cannot
  assign one) and carried, together with an optional device target and an optional opaque
  sealed preview for push banners, as headers on `POST /api/items` rather than a JSON body or
  query params.
- Podman-based dev and prod compose stacks, a multi-stage Dockerfile, and a Helm chart for
  Kubernetes deployment.
