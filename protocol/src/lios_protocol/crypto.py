"""AES-256-GCM sealing of one opaque blob under the shared group key.

The relay stores and forwards exactly what this module produces and can never open it -- the
group key never reaches the relay (see :mod:`lios_protocol.pairing`). Every seal uses a fresh
random 96-bit nonce, prepended to the ciphertext so the wire representation is a single
self-contained blob with nothing else to track alongside it.
"""

from __future__ import annotations

import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

#: AES-256 key size in bytes.
KEY_SIZE = 32

#: GCM nonce size in bytes -- 96 bits, the size AES-GCM is designed for.
NONCE_SIZE = 12


class TamperError(ValueError):
    """The blob's authentication tag did not verify: wrong key, or the bytes were altered.

    A subclass of ValueError rather than a bare exception, so a caller that already handles
    malformed input the same way does not need a second except clause.
    """


def generate_group_key() -> bytes:
    """Generate a fresh 256-bit key for a new device fleet, from the OS CSPRNG."""
    return os.urandom(KEY_SIZE)


def seal(key: bytes, plaintext: bytes, *, associated_data: bytes = b"") -> bytes:
    """Encrypt `plaintext` under `key`, returning nonce || ciphertext || tag as one blob.

    `associated_data` is authenticated but not encrypted -- pass the item's clear-text
    metadata (id, size, timestamps) here so a swapped envelope on a genuine item is rejected
    even though the relay never inspects the blob's contents.

    Raises:
        ValueError: `key` is not exactly 32 bytes.
    """
    if len(key) != KEY_SIZE:
        raise ValueError(f"group key must be {KEY_SIZE} bytes, got {len(key)}")
    nonce = os.urandom(NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, associated_data or None)
    return nonce + ciphertext


def open_sealed(key: bytes, blob: bytes, *, associated_data: bytes = b"") -> bytes:
    """Decrypt a blob produced by :func:`seal`, verifying its tag and `associated_data`.

    Raises:
        ValueError: `key` is not exactly 32 bytes, or `blob` is shorter than one nonce.
        TamperError: the tag does not verify -- wrong key, wrong associated_data, or the blob
            was altered in transit or at rest.
    """
    if len(key) != KEY_SIZE:
        raise ValueError(f"group key must be {KEY_SIZE} bytes, got {len(key)}")
    if len(blob) < NONCE_SIZE:
        raise ValueError(f"sealed blob shorter than one nonce ({NONCE_SIZE} bytes)")
    nonce, ciphertext = blob[:NONCE_SIZE], blob[NONCE_SIZE:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, associated_data or None)
    except InvalidTag as exc:
        raise TamperError("sealed blob failed authentication") from exc
