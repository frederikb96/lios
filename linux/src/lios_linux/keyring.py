"""Secrets at rest -- the device token and the fleet's group key -- via the Secret Service.

Not a file on disk: both are exactly what an attacker with read access to the Flatpak's data
directory would want (spec row 61, "Keys at rest"). `libsecret` reaches the Secret Service
(GNOME Keyring) over the session bus; the Flatpak manifest needs
`--talk-name=org.freedesktop.secrets` for it, a filtered D-Bus name grant `xdg-dbus-proxy`
allows without opening the whole session bus (`--socket=session-bus`), which the rest of the
manifest deliberately stays away from.

Untestable in this environment without a running, unlocked Secret Service daemon -- `pai-vm`
has no desktop session and so no keyring to store into. Synchronous calls: both secrets are
read once at startup and written only at pairing, never on a hot path, so blocking briefly is
an acceptable trade against building a second async pattern alongside `relaylink.client`'s.
"""

from __future__ import annotations

import base64

import gi

gi.require_version("Secret", "1")
gi.require_version("GLib", "2.0")

from gi.repository import GLib, Secret  # noqa: E402

_SCHEMA = Secret.Schema.new(
    "io.github.frederikb96.Lios",
    Secret.SchemaFlags.NONE,
    {"kind": Secret.SchemaAttributeType.STRING},
)

_DEVICE_TOKEN_ATTRS = {"kind": "device_token"}
_GROUP_KEY_ATTRS = {"kind": "group_key"}


class SecretNotFound(RuntimeError):
    """Nothing is stored under the requested attributes, or the Secret Service itself is
    unreachable (no keyring daemon running at all) -- either way, this device is not paired
    with a usable credential right now."""


def _lookup(attributes: dict[str, str]) -> str | None:
    """`Secret.password_lookup_sync`, folding "service unreachable" into "not found".

    `libsecret` raises `GLib.Error` rather than returning `None` when there is no Secret
    Service on the bus at all (as opposed to the service being reachable but holding nothing
    under these attributes) -- both are the same "no usable secret right now" to every caller
    here.
    """
    try:
        value = Secret.password_lookup_sync(_SCHEMA, attributes, None)
        return str(value) if value is not None else None
    except GLib.Error:
        return None


def store_device_token(token: str) -> None:
    """Persist the bearer token issued at `POST /api/devices/pair`."""
    Secret.password_store_sync(
        _SCHEMA,
        _DEVICE_TOKEN_ATTRS,
        Secret.COLLECTION_DEFAULT,
        "LIOS device token",
        token,
        None,
    )


def load_device_token() -> str:
    """
    Raises:
        SecretNotFound: this device has not completed pairing.
    """
    value = _lookup(_DEVICE_TOKEN_ATTRS)
    if value is None:
        raise SecretNotFound("no device token stored -- pair this device first")
    return str(value)


def store_group_key(group_key: bytes) -> None:
    """Persist the fleet's shared AEAD key. `libsecret`'s API is string-valued, hence base64."""
    Secret.password_store_sync(
        _SCHEMA,
        _GROUP_KEY_ATTRS,
        Secret.COLLECTION_DEFAULT,
        "LIOS group key",
        base64.b64encode(group_key).decode("ascii"),
        None,
    )


def load_group_key() -> bytes:
    """
    Raises:
        SecretNotFound: this device has not completed pairing.
    """
    value = _lookup(_GROUP_KEY_ATTRS)
    if value is None:
        raise SecretNotFound("no group key stored -- pair this device first")
    return base64.b64decode(value)


def clear_all() -> None:
    """Remove both secrets -- called before starting a fresh pairing."""
    Secret.password_clear_sync(_SCHEMA, _DEVICE_TOKEN_ATTRS, None)
    Secret.password_clear_sync(_SCHEMA, _GROUP_KEY_ATTRS, None)


def is_paired() -> bool:
    """Whether this device has completed pairing -- both secrets are present."""
    try:
        load_device_token()
        load_group_key()
    except SecretNotFound:
        return False
    return True
