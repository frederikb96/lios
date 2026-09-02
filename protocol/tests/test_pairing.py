"""Tests for :mod:`lios_protocol.pairing` -- payload construction and the QR round trip."""

from __future__ import annotations

import pytest

from lios_protocol.crypto import generate_group_key
from lios_protocol.pairing import (
    _CODE_ALPHABET,
    build_pairing_payload,
    decode_qr_uri,
    encode_qr_uri,
    generate_pairing_code,
)


def test_generate_pairing_code_default_length() -> None:
    assert len(generate_pairing_code()) == 8


def test_generate_pairing_code_custom_length() -> None:
    assert len(generate_pairing_code(length=12)) == 12


def test_generate_pairing_code_uses_unambiguous_alphabet() -> None:
    code = generate_pairing_code(length=64)
    assert set(code) <= set(_CODE_ALPHABET)
    assert set(code).isdisjoint({"0", "O", "1", "I", "L"})


def test_generate_pairing_code_is_random() -> None:
    assert generate_pairing_code() != generate_pairing_code()


def test_build_pairing_payload_round_trips_key() -> None:
    key = generate_group_key()
    payload = build_pairing_payload(
        relay_url="https://lios.example.net", pairing_code="ABCD1234", group_key=key
    )
    assert payload.group_key() == key


def test_build_pairing_payload_rejects_wrong_key_size() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        build_pairing_payload(
            relay_url="https://lios.example.net", pairing_code="ABCD1234", group_key=b"short"
        )


def test_encode_decode_qr_uri_round_trip() -> None:
    key = generate_group_key()
    payload = build_pairing_payload(
        relay_url="https://lios.example.net", pairing_code="ABCD1234", group_key=key
    )
    uri = encode_qr_uri(payload)
    assert uri.startswith("lios://pair/")

    decoded = decode_qr_uri(uri)
    assert decoded == payload
    assert decoded.group_key() == key


def test_decode_qr_uri_rejects_wrong_scheme() -> None:
    with pytest.raises(ValueError, match="LIOS pairing URI"):
        decode_qr_uri("https://example.com/not-a-pairing-uri")


def test_decode_qr_uri_rejects_garbage_payload() -> None:
    with pytest.raises(ValueError):
        decode_qr_uri("lios://pair/not-valid-base64-json!!!")
