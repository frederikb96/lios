"""Spawning a helper process through `Gio.Subprocess`, which reaps its children automatically.

An unreaped forked helper is exactly what turned into "zombie wl-copy processes" during the
migration away from wl-copy in Freddy's speech-to-text tool (report
5b69b919-ed12-4092-8de0-1237b5c8b143, section 4) -- that history was a spawning bug (`Popen`
without `wait()`), not a Wayland one. `Gio.Subprocess.communicate()` waits for and reaps the
child itself, so nothing built on this module can repeat it.

Blocking: `run()` waits for the child to exit. Every call site in this application (`wl.py`)
is expected to run off the GTK main thread, the same way any blocking I/O would be.
"""

from __future__ import annotations

from collections.abc import Mapping

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")

from gi.repository import Gio, GLib  # noqa: E402


class HelperError(RuntimeError):
    """A spawned helper could not be started, or exited non-zero."""


def run(
    argv: list[str],
    *,
    stdin: bytes | None = None,
    env_extra: Mapping[str, str] | None = None,
) -> bytes:
    """Run `argv` to completion, feeding it `stdin` if given, and return its stdout.

    `env_extra` is added on top of the inherited environment -- used to pass
    `XDG_ACTIVATION_TOKEN` through to `wl-copy`/`wl-paste` so they perform a sanctioned
    Wayland activation instead of the zero-timestamp fallback when a token is available.

    Raises:
        HelperError: `argv[0]` could not be spawned, or the process exited non-zero. stderr is
            folded into the message when the process produced any.
    """
    flags = Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
    if stdin is not None:
        flags |= Gio.SubprocessFlags.STDIN_PIPE
    launcher = Gio.SubprocessLauncher.new(flags)
    for key, value in (env_extra or {}).items():
        launcher.setenv(key, value, True)

    try:
        process = launcher.spawnv(argv)
    except GLib.Error as exc:
        raise HelperError(f"could not spawn {argv[0]!r}: {exc}") from exc

    stdin_bytes = GLib.Bytes.new(stdin) if stdin is not None else None
    _ok, stdout_bytes, stderr_bytes = process.communicate(stdin_bytes, None)

    if not process.get_successful():
        stderr = stderr_bytes.get_data().decode("utf-8", errors="replace") if stderr_bytes else ""
        raise HelperError(
            f"{argv[0]} exited {process.get_exit_status()}"
            + (f": {stderr.strip()}" if stderr.strip() else "")
        )
    return stdout_bytes.get_data() if stdout_bytes else b""
