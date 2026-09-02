"""`Gio.Subprocess`-based spawning -- needs no Wayland session, so genuinely testable headless.

Runs real processes (`/bin/cat`, `/bin/false`, `/bin/sh`) rather than mocking `Gio.Subprocess`,
since the whole point is proving the reap-and-report behaviour actually happens.
"""

from __future__ import annotations

import pytest

from lios_linux.clipboard.subprocess_runner import HelperError, run


def test_stdin_is_piped_to_stdout() -> None:
    assert run(["/bin/cat"], stdin=b"hello world") == b"hello world"


def test_no_stdin_still_runs() -> None:
    assert run(["/bin/echo", "-n", "hi"]) == b"hi"


def test_nonzero_exit_raises_helper_error() -> None:
    with pytest.raises(HelperError, match="exited 1"):
        run(["/bin/false"])


def test_stderr_is_folded_into_the_error_message() -> None:
    with pytest.raises(HelperError, match="boom"):
        run(["/bin/sh", "-c", "echo boom >&2; exit 3"])


def test_missing_binary_raises_helper_error_rather_than_hanging() -> None:
    with pytest.raises(HelperError, match="could not spawn"):
        run(["/no/such/binary-lios-test"])


def test_env_extra_is_visible_to_the_child() -> None:
    output = run(["/bin/sh", "-c", "echo -n $LIOS_TEST_VAR"], env_extra={"LIOS_TEST_VAR": "xyz"})
    assert output == b"xyz"
