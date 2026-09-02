"""The two pairing roles: an already-paired device minting a QR for a new one, and a fresh
device redeeming a scanned (or typed) code.

The group key never touches the relay in either direction (the design) -- it travels only
inside the QR payload `lios_protocol.pairing` builds and decodes, entirely client-side. This
module is the glue between that library, the relay's pairing endpoints (`relaylink.rest`), and
where the two secrets end up locally (`lios_linux.keyring`).

Untestable end to end in this environment without a running relay; `lios_protocol.pairing`
itself (the QR payload encode/decode this module calls) is already unit-tested in the
`protocol` package.
"""

from __future__ import annotations

import gi

gi.require_version("Soup", "3.0")

from gi.repository import Soup  # noqa: E402
from lios_protocol.crypto import generate_group_key  # noqa: E402
from lios_protocol.pairing import (  # noqa: E402
    PairingPayload,
    build_pairing_payload,
    decode_qr_uri,
    encode_qr_uri,
)

from lios_linux import keyring  # noqa: E402
from lios_linux.relaylink import rest  # noqa: E402

#: How this device identifies itself to the relay and to a human reading the device list.
_DISPLAY_NAME = "Linux"


def start_first_device(*, relay_url: str, session: Soup.Session) -> None:
    """Bootstrap a brand-new fleet: generate the group key, register this device against the
    relay's still-empty registry, and store both secrets locally.

    There is no pairing code to redeem for the very first device -- nothing exists yet to mint
    one on its behalf. `POST /api/devices/bootstrap` is the one relay call that needs no
    token, and only while the device registry is empty; every later device joins through
    :func:`redeem_pairing_qr` instead.

    Raises:
        relaylink.rest.RelayError: a device is already registered (this is not the first
            device), or the call otherwise failed.
    """
    paired = rest.bootstrap_first_device(session, relay_url=relay_url, display_name=_DISPLAY_NAME)
    keyring.store_device_token(paired.device_token)
    keyring.store_group_key(generate_group_key())


def generate_pairing_qr(*, relay_url: str, session: Soup.Session) -> str:
    """From an already-paired device: mint a pairing code and return the QR's URI text.

    Raises:
        relaylink.rest.RelayError: the relay call failed.
        keyring.SecretNotFound: this device has not paired yet.
    """
    device_token = keyring.load_device_token()
    group_key = keyring.load_group_key()
    pairing_session = rest.create_pairing_session(
        session, relay_url=relay_url, device_token=device_token
    )
    payload = build_pairing_payload(
        relay_url=relay_url, pairing_code=pairing_session.pairing_code, group_key=group_key
    )
    return encode_qr_uri(payload)


def redeem_pairing_qr(*, uri: str, session: Soup.Session) -> None:
    """From a new device: decode a scanned (or typed) QR URI and complete pairing.

    Stores the device token and the group key in the Secret Service on success. Never partial:
    if the relay call fails, nothing is written.

    Raises:
        ValueError: `uri` is not a well-formed LIOS pairing URI.
        relaylink.rest.RelayError: the relay rejected the code (expired, already redeemed, or
            never existed) or the call otherwise failed.
    """
    payload: PairingPayload = decode_qr_uri(uri)
    paired = rest.pair_device(
        session,
        relay_url=payload.relay_url,
        pairing_code=payload.pairing_code,
        display_name=_DISPLAY_NAME,
    )
    keyring.store_device_token(paired.device_token)
    keyring.store_group_key(payload.group_key())


__all__ = [
    "generate_group_key",
    "generate_pairing_qr",
    "redeem_pairing_qr",
    "start_first_device",
]
