"""The `wl-copy`/`wl-paste` clipboard backend -- used for every clipboard touch except an
in-window button click (see :mod:`gdk`).

Untestable in this environment: every function here needs a live Wayland session, which
`this machine` (headless) does not have. `subprocess_runner.run` underneath is unit-tested against
real processes; what is not exercised here is `wl-copy`/`wl-paste` actually reaching a
compositor. The type-priority decision (:mod:`priority`) that decides *what* to read is
already fully unit-tested and used unchanged here.
"""

from __future__ import annotations

from lios_linux.clipboard.priority import ClipboardChoice, ClipboardKind, choose_read_type
from lios_linux.clipboard.subprocess_runner import HelperError, run

#: `wl-paste`/`wl-copy` read `$XDG_ACTIVATION_TOKEN` (and `$DESKTOP_STARTUP_ID`) and, when
#: present, call `xdg_activation_v1.activate()` instead of relying on the zero-timestamp
#: focus-stealing-prevention bypass -- a sanctioned activation rather than a trick, whenever
#: the caller has a token to hand (a GlobalShortcuts activation, or a notification click).
_ACTIVATION_TOKEN_ENV = "XDG_ACTIVATION_TOKEN"


def _env_for(activation_token: str | None) -> dict[str, str]:
    return {_ACTIVATION_TOKEN_ENV: activation_token} if activation_token else {}


def write_text(text: str, *, activation_token: str | None = None) -> None:
    """Put `text` on the clipboard as UTF-8 plain text."""
    run(
        ["wl-copy", "--type", "text/plain;charset=utf-8"],
        stdin=text.encode("utf-8"),
        env_extra=_env_for(activation_token),
    )


def write_image_png(data: bytes, *, activation_token: str | None = None) -> None:
    """Put `data` (already-encoded PNG bytes) on the clipboard as an image."""
    run(
        ["wl-copy", "--type", "image/png"],
        stdin=data,
        env_extra=_env_for(activation_token),
    )


def list_types() -> list[str]:
    """Every mime type the clipboard currently offers, as `wl-paste --list-types` reports them."""
    output = run(["wl-paste", "--list-types"])
    return [line for line in output.decode("utf-8", errors="replace").splitlines() if line]


def read_bytes(mime_type: str) -> bytes:
    """Read the clipboard's content as `mime_type`, raw."""
    return run(["wl-paste", "--no-newline", "--type", mime_type])


class NothingOnClipboard(RuntimeError):
    """The clipboard is empty, or holds only types this priority list has no rule for."""


def read_best() -> tuple[ClipboardChoice, bytes]:
    """List the clipboard's types, pick the best one by priority, and read it.

    The two `wl-paste` calls (list, then read) each briefly steal focus -- unavoidable, and
    why this is only ever called on an explicit trigger, never a poll.

    Raises:
        NothingOnClipboard: nothing on the clipboard matched any priority tier.
        HelperError: `wl-paste` failed outright (no Wayland session, no clipboard owner, etc).
    """
    choice = choose_read_type(list_types())
    if choice is None:
        raise NothingOnClipboard("clipboard is empty or holds no type this app understands")
    return choice, read_bytes(choice.mime_type)


__all__ = [
    "ClipboardChoice",
    "ClipboardKind",
    "HelperError",
    "NothingOnClipboard",
    "list_types",
    "read_best",
    "read_bytes",
    "write_image_png",
    "write_text",
]
