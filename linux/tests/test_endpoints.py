"""Pure URL/header construction against the relay -- no network involved."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lios_linux.relaylink import endpoints


def test_items_url_without_target() -> None:
    assert endpoints.items_url("https://relay.example.com") == "https://relay.example.com/api/items"


def test_items_url_with_target_narrows_delivery() -> None:
    url = endpoints.items_url("https://relay.example.com", target_device_id="abc-123")
    assert url == "https://relay.example.com/api/items?target_device_id=abc-123"


def test_create_item_headers_carries_bearer_and_item_id() -> None:
    headers = endpoints.create_item_headers(
        device_token="secret-token", item_id="item-1", content_length=42
    )
    assert headers["Authorization"] == "Bearer secret-token"
    assert headers["Content-Type"] == "application/octet-stream"
    assert headers["Content-Length"] == "42"
    assert headers["X-Item-Id"] == "item-1"
    assert "X-Sealed-Preview" not in headers


def test_create_item_headers_with_sealed_preview() -> None:
    headers = endpoints.create_item_headers(
        device_token="secret-token",
        item_id="item-1",
        content_length=42,
        sealed_preview=b"sealed-bytes",
    )
    assert headers["X-Sealed-Preview"] == "c2VhbGVkLWJ5dGVz"


def test_trailing_slash_on_relay_url_is_stripped() -> None:
    assert endpoints.item_url("https://relay.example.com/", "xyz") == (
        "https://relay.example.com/api/items/xyz"
    )


def test_items_since_url_encodes_an_iso_timestamp() -> None:
    since = datetime(2026, 1, 1, tzinfo=UTC)
    url = endpoints.items_since_url("https://relay.example.com", since)
    assert url.startswith("https://relay.example.com/api/items?since=")
    assert "2026-01-01" in url


def test_stream_url_upgrades_https_to_wss() -> None:
    assert (
        endpoints.stream_url("https://relay.example.com")
        == "wss://relay.example.com/api/stream"
    )


def test_stream_url_upgrades_http_to_ws() -> None:
    assert endpoints.stream_url("http://localhost:8000") == "ws://localhost:8000/api/stream"


def test_stream_url_rejects_a_non_http_scheme() -> None:
    with pytest.raises(ValueError, match="http"):
        endpoints.stream_url("ftp://relay.example.com")


def test_auth_header_carries_a_bearer_token() -> None:
    assert endpoints.auth_header("secret-token") == {"Authorization": "Bearer secret-token"}


def test_push_token_url_quotes_the_device_id() -> None:
    url = endpoints.push_token_url("https://relay.example.com", "abc/def")
    assert url == "https://relay.example.com/api/devices/abc%2Fdef/push-token"
