# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `lios-protocol`: shared AES-256-GCM sealing, metadata/payload framing, QR-based device
  pairing, and the Pydantic wire types the relay and every client build against.
- `lios-relay`: a FastAPI service storing sealed items, tracking per-device acknowledgements
  against a per-item recipient snapshot, pruning on a configurable retention policy, and
  pushing a generic APNs notification when a recipient is an iOS device with a registered
  token. WebSocket stream for live delivery, bearer device-token auth throughout, a
  first-device bootstrap endpoint, Postgres via SQLAlchemy async + Alembic.
- Podman-based dev and prod compose stacks, a multi-stage Dockerfile, and a Helm chart for
  Kubernetes deployment.
