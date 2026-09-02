"""Command-line grammar -- the exported CLI fallback for desktops with no GlobalShortcuts
portal (the design)."""

from __future__ import annotations

import pytest

from lios_linux.cli import Pair, SendClipboard, SendFile, ShowWindow, parse


def test_send_clipboard() -> None:
    assert parse(["send-clipboard"]) == SendClipboard()


def test_send_file_with_a_path() -> None:
    assert parse(["send-file", "/home/frederik/photo.png"]) == SendFile(
        path="/home/frederik/photo.png"
    )


def test_send_file_with_no_path_opens_a_chooser() -> None:
    assert parse(["send-file"]) == SendFile(path=None)


def test_pair_with_a_uri() -> None:
    assert parse(["pair", "lios://pair/abc"]) == Pair(uri="lios://pair/abc")


def test_pair_with_no_uri() -> None:
    assert parse(["pair"]) == Pair(uri=None)


def test_no_subcommand_shows_the_window() -> None:
    assert parse([]) == ShowWindow()


def test_explicit_show() -> None:
    assert parse(["show"]) == ShowWindow()


def test_unknown_subcommand_exits_rather_than_silently_falling_through() -> None:
    with pytest.raises(SystemExit):
        parse(["frobnicate"])
