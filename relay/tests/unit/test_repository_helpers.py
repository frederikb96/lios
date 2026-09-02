"""Pure-function tests for :mod:`lios_relay.database.repository` -- no database needed."""

from __future__ import annotations

from lios_relay.database.repository import generate_device_token, hash_token


def test_hash_token_is_deterministic() -> None:
    assert hash_token("abc") == hash_token("abc")


def test_hash_token_differs_for_different_input() -> None:
    assert hash_token("abc") != hash_token("abd")


def test_hash_token_is_not_the_raw_value() -> None:
    assert hash_token("my-secret-token") != "my-secret-token"


def test_generate_device_token_is_random_and_long() -> None:
    a, b = generate_device_token(), generate_device_token()
    assert a != b
    assert len(a) >= 32
