"""`LiosApplication._connect_to_relay_if_paired` keeps trying while the keyring is locked.

The Background portal starts this app at login, and the login keyring unlocks separately --
routinely a few seconds later. Until it does, the device token cannot be read and no relay
connection is possible. Giving up after the first attempt leaves a running app that is
permanently disconnected and looks, from every outside angle, exactly like a connected one
with nothing to deliver: the process is up, the window opens, the history simply stays empty.

Driven against a duck-typed stand-in rather than a real `LiosApplication`, whose `__init__`
wants a GTK application, a config directory and a history database -- none of which this
decision touches. `GLib.timeout_add_seconds` and `StreamConnection` are replaced so the retry
can be stepped by hand instead of waited for.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable

from lios_linux import app as app_module
from lios_linux import keyring
from lios_linux.app import LiosApplication


class _FakeStream:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.started = 0

    def start(self) -> None:
        self.started += 1


class _Stub:
    """Carries only the attributes the connect path reads."""

    _connect_to_relay_if_paired = LiosApplication._connect_to_relay_if_paired
    _schedule_keyring_retry = LiosApplication._schedule_keyring_retry
    _keyring_retry_tick = LiosApplication._keyring_retry_tick

    def __init__(self) -> None:
        self.config = SimpleNamespace(relay_url="https://example.invalid")
        self.soup_session = object()
        self._stream: _FakeStream | None = None
        self._keyring_attempt = 0

    def _on_item_announced(self, item: object) -> None: ...

    def _catch_up_since(self) -> None: ...


def _patch(
    monkeypatch: Any,
    *,
    token: Callable[[], str],
    scheduled: list[tuple[int, Callable[[], bool]]],
) -> None:
    monkeypatch.setattr(app_module.keyring, "load_device_token", lambda: token())
    monkeypatch.setattr(app_module, "StreamConnection", _FakeStream)
    monkeypatch.setattr(
        app_module.GLib,
        "timeout_add_seconds",
        lambda delay, callback: scheduled.append((delay, callback)),
    )


def test_a_locked_keyring_schedules_another_attempt(monkeypatch: Any) -> None:
    scheduled: list[tuple[int, Callable[[], bool]]] = []

    def locked() -> str:
        raise keyring.KeyringUnavailable("the default keyring is locked")

    _patch(monkeypatch, token=locked, scheduled=scheduled)
    stub = _Stub()

    stub._connect_to_relay_if_paired()

    assert stub._stream is None
    assert len(scheduled) == 1


def test_the_retry_connects_once_the_keyring_unlocks(monkeypatch: Any) -> None:
    """The whole point: the second attempt is the one that succeeds, and nothing external
    has to prompt it."""
    scheduled: list[tuple[int, Callable[[], bool]]] = []
    attempts = {"n": 0}

    def locked_then_open() -> str:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise keyring.KeyringUnavailable("the default keyring is locked")
        return "device-token"

    _patch(monkeypatch, token=locked_then_open, scheduled=scheduled)
    stub = _Stub()

    stub._connect_to_relay_if_paired()
    scheduled[0][1]()

    assert stub._stream is not None
    assert stub._stream.started == 1
    assert stub._stream.kwargs["device_token"] == "device-token"


def test_repeated_locked_attempts_back_off_rather_than_spinning(
    monkeypatch: Any,
) -> None:
    scheduled: list[tuple[int, Callable[[], bool]]] = []

    def locked() -> str:
        raise keyring.KeyringUnavailable("the default keyring is locked")

    _patch(monkeypatch, token=locked, scheduled=scheduled)
    stub = _Stub()

    for _ in range(6):
        stub._connect_to_relay_if_paired()

    assert len(scheduled) == 6
    assert scheduled[-1][0] > scheduled[0][0]


def test_an_established_stream_is_never_replaced(monkeypatch: Any) -> None:
    """Pairing calls this path again on an already-connected app; a second `StreamConnection`
    would hold a second socket and deliver every item twice."""
    scheduled: list[tuple[int, Callable[[], bool]]] = []
    _patch(monkeypatch, token=lambda: "device-token", scheduled=scheduled)
    stub = _Stub()

    stub._connect_to_relay_if_paired()
    first = stub._stream
    stub._connect_to_relay_if_paired()

    assert stub._stream is first
    assert first is not None
    assert first.started == 1


def test_an_unpaired_device_does_not_retry(monkeypatch: Any) -> None:
    """No token stored is a settled answer, not a transient one -- pairing calls back in."""
    scheduled: list[tuple[int, Callable[[], bool]]] = []

    def missing() -> str:
        raise keyring.SecretNotFound("no token")

    _patch(monkeypatch, token=missing, scheduled=scheduled)
    stub = _Stub()

    stub._connect_to_relay_if_paired()

    assert stub._stream is None
    assert scheduled == []
