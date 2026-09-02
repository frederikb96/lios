"""Round-trip and tamper-detection tests for :mod:`lios_protocol.crypto`."""

from __future__ import annotations

import pytest

from lios_protocol.crypto import KEY_SIZE, TamperError, generate_group_key, open_sealed, seal


def test_generate_group_key_is_right_size() -> None:
    assert len(generate_group_key()) == KEY_SIZE


def test_generate_group_key_is_random() -> None:
    assert generate_group_key() != generate_group_key()


def test_seal_open_round_trip() -> None:
    key = generate_group_key()
    plaintext = b"hello from the clipboard"
    blob = seal(key, plaintext)
    assert open_sealed(key, blob) == plaintext


def test_seal_open_round_trip_empty_plaintext() -> None:
    key = generate_group_key()
    blob = seal(key, b"")
    assert open_sealed(key, blob) == b""


def test_seal_is_nondeterministic() -> None:
    """Two seals of the same plaintext differ -- each draws a fresh random nonce."""
    key = generate_group_key()
    assert seal(key, b"same content") != seal(key, b"same content")


def test_open_wrong_key_raises_tamper_error() -> None:
    blob = seal(generate_group_key(), b"secret")
    with pytest.raises(TamperError):
        open_sealed(generate_group_key(), blob)


def test_open_flipped_byte_raises_tamper_error() -> None:
    key = generate_group_key()
    blob = bytearray(seal(key, b"secret"))
    blob[-1] ^= 0xFF
    with pytest.raises(TamperError):
        open_sealed(key, bytes(blob))


def test_associated_data_is_authenticated() -> None:
    key = generate_group_key()
    blob = seal(key, b"secret", associated_data=b"item-id-1")

    with pytest.raises(TamperError):
        open_sealed(key, blob, associated_data=b"item-id-2")

    assert open_sealed(key, blob, associated_data=b"item-id-1") == b"secret"


def test_seal_rejects_wrong_key_size() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        seal(b"too-short", b"secret")


def test_open_rejects_wrong_key_size() -> None:
    blob = seal(generate_group_key(), b"secret")
    with pytest.raises(ValueError, match="32 bytes"):
        open_sealed(b"too-short", blob)


def test_open_rejects_blob_shorter_than_nonce() -> None:
    with pytest.raises(ValueError, match="nonce"):
        open_sealed(generate_group_key(), b"short")
