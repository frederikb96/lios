"""pg-layer fixtures: a migrated database, an ASGI test client wired to it, and two paired
devices to exercise the item flow against."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.network import Network

from lios_relay.config import reset_config
from lios_relay.database.connection import DatabaseConnection, close_database, init_database
from lios_relay.database.repository import create_device, generate_device_token
from lios_relay.server import create_app
from lios_relay.server_state import reset_broadcaster
from tests.setup.migrations import run_migrations
from tests.setup.runtime import bootstrap_container_runtime, owner_labels

POSTGRES_DB = "lios"
POSTGRES_USER = "lios"
POSTGRES_PASSWORD = "lios-test"  # noqa: S105 -- throwaway, container-local only


@pytest.fixture(scope="session")
def _container_runtime() -> None:
    """Bootstrap DOCKER_HOST once per test session before any container starts.

    Deliberately not autouse: every container fixture below depends on it explicitly, so a
    unit-only run (`pytest -m unit`) never probes for a runtime it does not need.
    """
    bootstrap_container_runtime()


@pytest.fixture(scope="session")
def test_network(_container_runtime: None) -> Iterator[Network]:
    with Network() as network:
        yield network


@pytest.fixture(scope="session")
def postgres_container(test_network: Network) -> Iterator[PostgresContainer]:
    with (
        PostgresContainer(
            "docker.io/postgres:17-alpine",
            dbname=POSTGRES_DB, username=POSTGRES_USER, password=POSTGRES_PASSWORD,
        )
        .with_network(test_network)
        .with_kwargs(labels=owner_labels())
    ) as pg:
        yield pg


@pytest.fixture(scope="session")
def postgres_url(postgres_container: PostgresContainer) -> str:
    """asyncpg-format connection URL for the started Postgres, from the host side."""
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    return f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{host}:{port}/{POSTGRES_DB}"


@pytest_asyncio.fixture()
async def migrated_db(postgres_url: str) -> AsyncIterator[DatabaseConnection]:
    """A `DatabaseConnection` to a Postgres migrated with the relay's own Alembic head, with
    every table truncated first.

    Function-scoped even though the container is session-scoped: each test gets a fresh
    global `DatabaseConnection` (and a fresh config instance, since `LIOS_DATABASE_URL` is
    the same across tests but the config singleton must not survive between them). The
    truncate is what makes tests independent of execution order despite sharing one
    session-scoped container -- most tests would tolerate leftover rows from an earlier
    test, but one asserting the device registry starts empty (bootstrap) cannot.
    """
    await run_migrations(postgres_url)
    os.environ["LIOS_DATABASE_URL"] = postgres_url
    reset_config()

    db = await init_database_for_url(postgres_url)
    async with db.session() as session:
        await session.execute(
            text("TRUNCATE devices, pairing_sessions, items, item_recipients, item_acks CASCADE")
        )
    try:
        yield db
    finally:
        await close_database()
        reset_config()


async def init_database_for_url(database_url: str) -> DatabaseConnection:
    """Initialize the global `DatabaseConnection` against a specific URL."""
    from lios_relay.config.loader import DatabaseConfig

    return await init_database(DatabaseConfig(url=database_url, pool_size=5, max_overflow=0))


@pytest_asyncio.fixture()
async def client(migrated_db: DatabaseConnection) -> AsyncIterator[AsyncClient]:
    """An `httpx.AsyncClient` driving the relay's ASGI app in-process, no network involved."""
    reset_broadcaster()
    app = create_app()
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture()
async def laptop_token(migrated_db: DatabaseConnection) -> str:
    """A directly-registered Linux device, standing in for "the first device in the fleet" --
    the one every pairing-session test starts from, since pairing itself needs an existing
    device to request a code."""
    token = generate_device_token()
    async with migrated_db.session() as session:
        await create_device(session, display_name="Test Laptop", platform="linux", token=token)
    return token


@pytest_asyncio.fixture()
async def phone_token(migrated_db: DatabaseConnection) -> str:
    """A second directly-registered device (iOS), standing in for a paired phone."""
    token = generate_device_token()
    async with migrated_db.session() as session:
        await create_device(session, display_name="Test iPhone", platform="ios", token=token)
    return token


def auth_headers(token: str) -> dict[str, str]:
    """The bearer-auth header a test sends as the given device."""
    return {"Authorization": f"Bearer {token}"}


def new_uuid() -> uuid.UUID:
    """A fresh UUID, for tests asserting on an id that must not resolve to anything real."""
    return uuid.uuid4()
