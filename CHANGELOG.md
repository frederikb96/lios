# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
