"""`keyring.resolve_pairing_status` -- the one decision this module makes that needs no
Secret Service, `gi`, or GTK at all: folding a device's own local history in as
corroboration against a keyring that claims this device has never paired."""

from __future__ import annotations

from lios_linux.keyring import PairingStatus, resolve_pairing_status


def test_not_paired_with_no_history_stays_not_paired() -> None:
    assert (
        resolve_pairing_status(PairingStatus.NOT_PAIRED, history_has_items=False)
        is PairingStatus.NOT_PAIRED
    )


def test_not_paired_with_existing_history_becomes_unavailable() -> None:
    """A device holding local history has certainly paired before -- a keyring that
    disagrees is the one that's wrong, not the history."""
    assert (
        resolve_pairing_status(PairingStatus.NOT_PAIRED, history_has_items=True)
        is PairingStatus.UNAVAILABLE
    )


def test_unavailable_stays_unavailable_regardless_of_history() -> None:
    assert (
        resolve_pairing_status(PairingStatus.UNAVAILABLE, history_has_items=False)
        is PairingStatus.UNAVAILABLE
    )
    assert (
        resolve_pairing_status(PairingStatus.UNAVAILABLE, history_has_items=True)
        is PairingStatus.UNAVAILABLE
    )


def test_paired_stays_paired_regardless_of_history() -> None:
    assert (
        resolve_pairing_status(PairingStatus.PAIRED, history_has_items=False)
        is PairingStatus.PAIRED
    )
    assert (
        resolve_pairing_status(PairingStatus.PAIRED, history_has_items=True)
        is PairingStatus.PAIRED
    )
