#!/bin/bash
set -e
cd /app/relay

# Reinstall both packages in editable mode (picks up mounted source changes). Skip on
# failure (e.g. userns_mode: keep-id permission issues) -- the build-time install is still
# present and source is volume-mounted.
uv pip install --system --no-deps -e /app/protocol -e /app/relay 2>/dev/null || true

alembic upgrade head || true

# With userns_mode: keep-id, we already run as the host user (uid 1000). gosu is only
# needed when running as root to drop privileges.
if [ "$(id -u)" = "0" ]; then
    exec gosu appuser uvicorn lios_relay.server:create_app \
        --host 0.0.0.0 \
        --port 8080 \
        --reload \
        --reload-dir /app/relay/src \
        --factory \
        --timeout-graceful-shutdown 5 \
        "$@"
else
    exec uvicorn lios_relay.server:create_app \
        --host 0.0.0.0 \
        --port 8080 \
        --reload \
        --reload-dir /app/relay/src \
        --factory \
        --timeout-graceful-shutdown 5 \
        "$@"
fi
