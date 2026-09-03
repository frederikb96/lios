"""`app._should_quit_for_stale_build` -- the only decision `LiosApplication` makes about
exiting for a stale build that does not itself need a live `Gio.Application`."""

from __future__ import annotations

from lios_linux.app import _should_quit_for_stale_build


def test_not_stale_never_quits() -> None:
    assert not _should_quit_for_stale_build(
        stale=False, inflight_sends=0, window_visible=False
    )


def test_stale_but_sending_a_file_does_not_quit() -> None:
    """Quitting mid-send would lose the file -- it is gone once the worker's own process
    exits partway through, unlike a receive, which is recoverable via catch-up."""
    assert not _should_quit_for_stale_build(
        stale=True, inflight_sends=1, window_visible=False
    )


def test_stale_but_window_open_does_not_quit() -> None:
    """A visible window is not pulled out from under whoever has it open -- see
    `LiosWindow.set_stale_version` for how they are told instead."""
    assert not _should_quit_for_stale_build(
        stale=True, inflight_sends=0, window_visible=True
    )


def test_stale_idle_and_hidden_quits() -> None:
    assert _should_quit_for_stale_build(stale=True, inflight_sends=0, window_visible=False)
