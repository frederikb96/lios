#!/bin/bash
set -e
cd /app/relay
alembic upgrade head
exec python -m lios_relay "$@"
