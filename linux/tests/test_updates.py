"""`portals.updates.is_stale` -- the only decision that module makes without a live Flatpak
session helper on the bus."""

from __future__ import annotations

from lios_linux.portals.updates import is_stale


def test_matching_commits_are_not_stale() -> None:
    """Nothing has changed on disk since this process launched."""
    assert not is_stale({"running-commit": "abc123", "local-commit": "abc123"})


def test_differing_local_commit_is_stale() -> None:
    """A newer build was installed while this process kept running -- restarting would run
    different code than it is running now."""
    assert is_stale({"running-commit": "abc123", "local-commit": "def456"})


def test_missing_local_commit_is_not_stale() -> None:
    """The real portal always sends both keys -- this is a defensive default against
    something malformed being treated as "yes, stale" rather than "cannot tell"."""
    assert not is_stale({"running-commit": "abc123"})


def test_missing_running_commit_is_not_stale() -> None:
    assert not is_stale({"local-commit": "def456"})


def test_empty_payload_is_not_stale() -> None:
    assert not is_stale({})
