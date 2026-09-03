"""Secrets at rest -- the device token and the fleet's group key -- via the Secret Service.

Not a file on disk: both are exactly what an attacker with read access to the Flatpak's data
directory would want. `libsecret` reaches the Secret Service (GNOME Keyring) over the session
bus; the Flatpak manifest needs `--talk-name=org.freedesktop.secrets` for it, a filtered D-Bus
name grant `xdg-dbus-proxy` allows without opening the whole session bus
(`--socket=session-bus`), which the rest of the manifest deliberately stays away from.

Three situations must never be confused, because only one of them means "pair this device
again": nothing was ever stored here (`SecretNotFound`), the Secret Service is unreachable or
its default collection is locked (`KeyringUnavailable`), or the credential is present. The
simple `secret_password_*` API folds a locked or unreachable collection into the same result
as "not found" -- neither raises through it distinguishably -- so telling those apart means
going through the lower-level `Secret.Service`/`Secret.Collection` objects instead, which is
what every function below that can raise `KeyringUnavailable` does.

Untestable in a headless environment without a running, unlocked Secret Service daemon and no
desktop session, so no keyring to store into or read from. `PairingStatus` and
`resolve_pairing_status` hold the only decisions this module makes that do not need one, and
are tested without `gi` at all.

Synchronous calls throughout: both secrets are read at startup and on every window refresh,
never mid-upload on a hot path. Actively unlocking a locked collection can block on a human
answering a system prompt, which is a different order of blocking than a local D-Bus round
trip -- `try_unlock_default_collection` and `ensure_storage_ready` are the only two functions
here that do it, and both are documented as background-thread-only for that reason; nothing
that runs on the GTK main thread (a plain status check, an ordinary load) ever attempts to
unlock, it only reports that the collection is currently locked.
"""

from __future__ import annotations

import base64
import enum

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

#: Both need collections loaded (to resolve the "default"/"session" aliases at all) and a
#: session open (to transfer the secret values themselves).
_SERVICE_FLAGS = Secret.ServiceFlags.OPEN_SESSION | Secret.ServiceFlags.LOAD_COLLECTIONS


class SecretNotFound(RuntimeError):
    """Confirmed absent: the Secret Service was reachable, its default collection was
    unlocked, and nothing was stored under the requested attributes. This device has never
    completed pairing (or the credential was explicitly cleared) -- the only situation in
    which offering to pair again is the right response.
    """


class KeyringUnavailable(RuntimeError):
    """Not the same claim as `SecretNotFound`: this means "I cannot tell right now", not "you
    have not paired". Covers the Secret Service being unreachable, its default collection
    being locked and not unlockable, or that collection resolving to the same, non-persistent
    "session" collection GNOME wipes on logout. A caller that treats this the same as
    `SecretNotFound` -- offering to re-claim the relay as a fresh first device -- is doing
    something destructive on the strength of an error, not a confirmed fact.
    """


class PairingStatus(enum.Enum):
    """What `pairing_status()` established: paired, confirmed not paired, or -- distinct
    from both -- currently impossible to tell."""

    PAIRED = "paired"
    NOT_PAIRED = "not_paired"
    UNAVAILABLE = "unavailable"


def _get_service() -> Secret.Service:
    try:
        return Secret.Service.get_sync(_SERVICE_FLAGS, None)
    except GLib.Error as exc:
        raise KeyringUnavailable(f"Secret Service unreachable: {exc}") from exc


def _collection_for_alias(service: Secret.Service, alias: str) -> Secret.Collection | None:
    """`None` means no collection is currently assigned to `alias` -- for "default" this
    means nothing has ever been stored on this machine (a genuine, not-yet-paired state);
    for "session" it just means this Secret Service implementation has none, which is fine.
    """
    try:
        return Secret.Collection.for_alias_sync(
            service, alias, Secret.CollectionFlags.NONE, None
        )
    except GLib.Error as exc:
        raise KeyringUnavailable(f"could not resolve the '{alias}' keyring: {exc}") from exc


def try_unlock_default_collection() -> bool:
    """Ask the Secret Service to unlock its default collection, prompting the user if it can.

    Blocks until the prompt is answered or the Secret Service gives up on it -- call this
    from a background thread only, exactly like every other call in this codebase that can
    block on the network or on a human (`relaylink`, `pairing_flow`). Never call it from a
    plain status check that runs on the GTK main thread.

    Returns whether the default collection ended up unlocked. `False` covers the Secret
    Service being unreachable, the user cancelling the prompt, and there being no default
    collection to unlock in the first place -- a caller only cares whether trying again now
    makes sense.
    """
    try:
        service = _get_service()
        collection = _collection_for_alias(service, Secret.COLLECTION_DEFAULT)
    except KeyringUnavailable:
        return False
    if collection is None:
        return False
    if not collection.get_locked():
        return True
    try:
        service.unlock_sync([collection], None)
    except GLib.Error:
        return False
    return not collection.get_locked()


def ensure_storage_ready() -> None:
    """Confirm that storing a credential now would actually persist, before anything calls a
    relay endpoint that only works once (`POST /api/devices/bootstrap`) or consumes a
    one-time pairing code -- a storage failure discovered only after `store_device_token`
    would waste either. `pairing_flow` calls this first, always from a background thread.

    Raises:
        KeyringUnavailable: the Secret Service is unreachable, its default collection is
            locked and could not be unlocked, or "default" currently resolves to the same
            collection as "session" -- the specific failure this exists to catch, matching
            exactly what would make a credential vanish at the next logout.
    """
    service = _get_service()
    collection = _collection_for_alias(service, Secret.COLLECTION_DEFAULT)
    if collection is not None and collection.get_locked():
        if not try_unlock_default_collection():
            raise KeyringUnavailable(
                "the default keyring is locked and could not be unlocked"
            )
        collection = _collection_for_alias(service, Secret.COLLECTION_DEFAULT)

    session_collection = _collection_for_alias(service, Secret.COLLECTION_SESSION)
    if (
        collection is not None
        and session_collection is not None
        and collection.get_object_path() == session_collection.get_object_path()
    ):
        raise KeyringUnavailable(
            "the default keyring is the non-persistent session collection -- anything "
            "stored here would not survive logging out"
        )


def _lookup(attributes: dict[str, str]) -> str | None:
    """`Secret.password_lookup_sync`, but checked against the collection's own locked state
    first -- the simple API raises the same opaque `GLib.Error` for "locked" as it would for
    almost anything else going wrong, which is exactly the distinction this module exists to
    preserve rather than throw away.

    Never attempts to unlock: this runs on every window refresh, on the GTK main thread, and
    unlocking can block on a human. A locked collection is reported as `KeyringUnavailable`,
    not silently treated as "not found".
    """
    service = _get_service()
    collection = _collection_for_alias(service, Secret.COLLECTION_DEFAULT)
    if collection is not None and collection.get_locked():
        raise KeyringUnavailable(
            "the default keyring is locked -- unlock it and try again"
        )
    try:
        value = Secret.password_lookup_sync(_SCHEMA, attributes, None)
    except GLib.Error as exc:
        raise KeyringUnavailable(f"could not read from the keyring: {exc}") from exc
    return str(value) if value is not None else None


def store_device_token(token: str) -> None:
    """Persist the bearer token issued at `POST /api/devices/pair`.

    Raises:
        KeyringUnavailable: the store call itself failed. Callers should run
            `ensure_storage_ready()` first (`pairing_flow` does), so this is expected to be
            rare in practice -- a race after that check passed, not the common case.
    """
    try:
        Secret.password_store_sync(
            _SCHEMA,
            _DEVICE_TOKEN_ATTRS,
            Secret.COLLECTION_DEFAULT,
            "LIOS device token",
            token,
            None,
        )
    except GLib.Error as exc:
        raise KeyringUnavailable(f"could not store the device token: {exc}") from exc


def load_device_token() -> str:
    """
    Raises:
        SecretNotFound: this device has not completed pairing.
        KeyringUnavailable: cannot currently tell -- see the class docstring.
    """
    value = _lookup(_DEVICE_TOKEN_ATTRS)
    if value is None:
        raise SecretNotFound("no device token stored -- pair this device first")
    return str(value)


def store_group_key(group_key: bytes) -> None:
    """Persist the fleet's shared AEAD key. `libsecret`'s API is string-valued, hence base64.

    Raises:
        KeyringUnavailable: see `store_device_token`.
    """
    try:
        Secret.password_store_sync(
            _SCHEMA,
            _GROUP_KEY_ATTRS,
            Secret.COLLECTION_DEFAULT,
            "LIOS group key",
            base64.b64encode(group_key).decode("ascii"),
            None,
        )
    except GLib.Error as exc:
        raise KeyringUnavailable(f"could not store the group key: {exc}") from exc


def load_group_key() -> bytes:
    """
    Raises:
        SecretNotFound: this device has not completed pairing.
        KeyringUnavailable: cannot currently tell -- see the class docstring.
    """
    value = _lookup(_GROUP_KEY_ATTRS)
    if value is None:
        raise SecretNotFound("no group key stored -- pair this device first")
    return base64.b64decode(value)


def clear_all() -> None:
    """Remove both secrets -- called before starting a fresh pairing."""
    Secret.password_clear_sync(_SCHEMA, _DEVICE_TOKEN_ATTRS, None)
    Secret.password_clear_sync(_SCHEMA, _GROUP_KEY_ATTRS, None)


def pairing_status() -> PairingStatus:
    """Whether this device is paired, confirmed not paired, or the keyring cannot currently
    say which. Cheap and main-thread-safe: never attempts to unlock anything, so the worst
    case is one local D-Bus round trip per secret, not a wait on a human.

    Callers must never treat `UNAVAILABLE` the same as `NOT_PAIRED` -- see
    `resolve_pairing_status` for folding in a device's own local history as corroboration.
    """
    try:
        load_device_token()
        load_group_key()
    except KeyringUnavailable:
        return PairingStatus.UNAVAILABLE
    except SecretNotFound:
        return PairingStatus.NOT_PAIRED
    return PairingStatus.PAIRED


def resolve_pairing_status(status: PairingStatus, *, history_has_items: bool) -> PairingStatus:
    """A device holding local history has certainly paired before -- if the keyring reports
    `NOT_PAIRED` anyway, the keyring is the one that's wrong, not the history. Folds that
    contradiction into `UNAVAILABLE`, the answer that never offers to re-claim the relay.

    Never downgrades a genuine `UNAVAILABLE` (a locked or unreachable keyring is exactly that
    regardless of history) and never touches `PAIRED`. Pure and total: takes only the two
    facts it needs, so it is testable with no Secret Service, `gi`, or GTK at all.
    """
    if status is PairingStatus.NOT_PAIRED and history_has_items:
        return PairingStatus.UNAVAILABLE
    return status
