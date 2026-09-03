# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- The relay's live stream announced every new item to every connected device, including the
  one that had just uploaded it, and the catch-up list had the same gap -- a reconnecting or
  restarting client could pull its own item back out of `GET /api/items?since=`. Both now
  narrow to the item's actual recipient snapshot, so a sender is never told about its own
  upload through either path.
- The Linux client's history list only rebuilt itself on construction, after pairing, or
  when a notification for an item it didn't already know about was clicked -- so opening the
  window any other way (a shortcut, or simply reopening it) showed whatever was true the last
  time one of those had happened, and an item arriving while the window was already open
  didn't appear either. Reopening the window now always reloads the list, and the
  application tells the window directly whenever an item arrives or expires.
- The Linux client's keyring lookup folded an unreachable Secret Service and a locked
  collection into the same "nothing stored" result as a device that had genuinely never
  paired, offering to re-claim the relay as a brand-new first device on the strength of
  either. It now tells the three apart, corroborates against local history (a device holding
  received items has certainly paired before), and only ever offers to unlock or retry when
  the keyring itself is the problem.

## [0.1.2] - 2026-09-03

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
- A cold `lios --help` (or any parse error) never used to exit: `do_startup` held the process
  resident before its own arguments were even parsed. Residency now waits for a command that
  means to stick around (`show`, the internal `background`, or a `pair` that just succeeded).
- Autostart and D-Bus service activation used to invoke the app with no arguments, which meant
  "show the window" -- so granting autostart permission popped a window at every login. Both
  now invoke the new, windowless `lios background` instead.
- Catching up on an item sent while this device was offline never worked across a restart:
  the relay stream's catch-up window was captured fresh at connect time and never persisted,
  so every process start began from "now" and anything sent before that was lost the moment
  the relay's 7-day retention caught up with it. The watermark now survives in local history
  and resumes from wherever this device last left off.
- `POST /api/items` announced the new item on the stream and pushed it before the transaction
  that created it had committed, so a recipient reacting to either signal could fetch the item
  the instant it arrived and get a 404 for a row that was in the database all along. The item
  is committed first now.
- The history list rendered every timestamp in UTC regardless of the system's own timezone.
  Recent items now read as "Just now" or "N minutes ago"; anything older shows the local clock
  time, or a local date and time once it's no longer the same day.

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
