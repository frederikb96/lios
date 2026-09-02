# LIOS relay Dockerfile
# Multi-stage build: base -> dev (hot-reload) -> prod (baked source)
#
# /app mirrors the repository root: /app/protocol and /app/relay are siblings, exactly the
# path relay/pyproject.toml's `[tool.uv.sources] lios-protocol = { path = "../protocol" }`
# already expects -- no path rewriting needed between a checkout and this image.

# =============================================================================
# Base stage: Python runtime + uv
# =============================================================================
FROM python:3.13-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gosu \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 appuser

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# =============================================================================
# Dev stage: deps cached in image, source mounted at runtime
# =============================================================================
FROM base AS dev

COPY protocol/pyproject.toml protocol/README.md /app/protocol/
RUN mkdir -p /app/protocol/src/lios_protocol && touch /app/protocol/src/lios_protocol/__init__.py

COPY relay/pyproject.toml relay/README.md /app/relay/
RUN mkdir -p /app/relay/src/lios_relay && touch /app/relay/src/lios_relay/__init__.py
RUN uv pip install --system --no-cache-dir -e /app/protocol -e "/app/relay[dev]"

# Make site-packages writable for uid 1000 (userns_mode: keep-id compatibility)
RUN SITE_PKG=$(python3 -c "import sysconfig; print(sysconfig.get_path('purelib'))") && \
    chown -R 1000:1000 /app "$SITE_PKG" 2>/dev/null || true

# --max-time bounds curl itself rather than relying on --timeout to kill it -- --reload
# keeps the listening socket open across a worker crash (see compose.dev.yaml), so a plain
# curl -sf can hang on a connection that will never get a response instead of failing outright.
HEALTHCHECK --interval=5s --timeout=5s --retries=6 --start-period=30s \
    CMD curl -sf --max-time 3 http://localhost:8080/health || exit 1

COPY docker/entrypoint-dev.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

# =============================================================================
# Prod stage: source baked in, minimal image
# =============================================================================
FROM base AS prod

COPY protocol/ /app/protocol/
COPY relay/pyproject.toml relay/README.md /app/relay/
RUN mkdir -p /app/relay/src/lios_relay && touch /app/relay/src/lios_relay/__init__.py \
    && uv pip install --system --no-cache-dir /app/protocol /app/relay

COPY relay/src/ /app/relay/src/
COPY relay/config/ /app/relay/config/
COPY relay/alembic/ /app/relay/alembic/
COPY relay/alembic.ini /app/relay/

RUN uv pip install --system --no-cache-dir --no-deps /app/protocol /app/relay

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=30s \
    CMD curl -sf http://localhost:8080/health || exit 1

COPY docker/entrypoint-prod.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
WORKDIR /app/relay
USER appuser
ENTRYPOINT ["/entrypoint.sh"]
