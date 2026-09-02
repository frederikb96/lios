"""Device pairing: turning an already-paired device's group key into a QR payload, and back.

The group key travels only inside the payload this module builds -- never as a bare value a
caller could accidentally log, store, or send to the relay. `PairingPayload` is the only place
the key exists as a `str`; everywhere else in this package it is `bytes`, and nothing in this
module ever makes an HTTP call -- the relay is only ever handed a `pairing_code`, never a key.
"""

from __future__ import annotations

import base64
import secrets

from pydantic import BaseModel, Field

from lios_protocol.crypto import KEY_SIZE

#: URI scheme a QR code carries. Chosen over a bare JSON string so a general-purpose QR
#: scanner (not just the LIOS app) shows it as a recognisable, non-executable link rather
#: than raw text that looks like it could be pasted somewhere.
_SCHEME = "lios"

#: Characters a pairing code is drawn from -- no ambiguous glyphs (0/O, 1/I/L), since a code
#: may need to be read off a screen and typed by hand as a fallback to scanning.
_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


class PairingPayload(BaseModel):
    """Everything a new device needs to join the fleet, exactly as carried by the QR code."""

    relay_url: str
    pairing_code: str
    group_key_b64: str = Field(description="base64-encoded 32-byte AES-256-GCM group key")

    def group_key(self) -> bytes:
        """Decode the embedded group key back to raw bytes.

        Raises:
            ValueError: the decoded key is not exactly 32 bytes.
        """
        key = base64.b64decode(self.group_key_b64)
        if len(key) != KEY_SIZE:
            raise ValueError(
                f"pairing payload's group key is {len(key)} bytes, expected {KEY_SIZE}"
            )
        return key


def generate_pairing_code(length: int = 8) -> str:
    """A short-lived, single-use code the relay mints and a redeeming device types or scans.

    Drawn from `secrets.choice` over an unambiguous alphabet -- this is a credential, not a
    display label, even though it is short enough to type by hand as a fallback.
    """
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def build_pairing_payload(
    *, relay_url: str, pairing_code: str, group_key: bytes
) -> PairingPayload:
    """Assemble the payload an already-paired device encodes into a QR code.

    Raises:
        ValueError: `group_key` is not exactly 32 bytes.
    """
    if len(group_key) != KEY_SIZE:
        raise ValueError(f"group key must be {KEY_SIZE} bytes, got {len(group_key)}")
    return PairingPayload(
        relay_url=relay_url,
        pairing_code=pairing_code,
        group_key_b64=base64.b64encode(group_key).decode("ascii"),
    )


def encode_qr_uri(payload: PairingPayload) -> str:
    """Render a `PairingPayload` as the URI a QR code image encodes.

    Rendering the actual QR code image is a client concern (`qrcode` on Linux, CoreImage's
    `CIQRCodeGenerator` on iOS) -- this only produces the string both sides agree on.
    """
    encoded = base64.urlsafe_b64encode(payload.model_dump_json().encode("utf-8")).decode("ascii")
    return f"{_SCHEME}://pair/{encoded}"


def decode_qr_uri(uri: str) -> PairingPayload:
    """Reverse :func:`encode_qr_uri`.

    Raises:
        ValueError: `uri` does not carry the expected scheme, or its payload does not parse.
    """
    prefix = f"{_SCHEME}://pair/"
    if not uri.startswith(prefix):
        raise ValueError(f"not a LIOS pairing URI: expected a {prefix!r} prefix")
    encoded = uri[len(prefix):]
    padded = encoded + "=" * (-len(encoded) % 4)
    decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    return PairingPayload.model_validate_json(decoded)
