"""Command-line grammar -- `lios show`, the one entry point any desktop's own keybinding
settings can bind, and `lios background`, the internal one autostart and the D-Bus service
file use."""

from __future__ import annotations

import pytest

from lios_linux.cli import Pair, RunBackground, ShowWindow, parse


def test_pair_with_a_uri() -> None:
    assert parse(["pair", "lios://pair/abc"]) == Pair(uri="lios://pair/abc")


def test_pair_with_no_uri() -> None:
    assert parse(["pair"]) == Pair(uri=None)


def test_no_subcommand_shows_the_window() -> None:
    assert parse([]) == ShowWindow()


def test_explicit_show() -> None:
    assert parse(["show"]) == ShowWindow()


def test_background_does_not_show_the_window() -> None:
    assert parse(["background"]) == RunBackground()


def test_help_exits_rather_than_returning_a_command() -> None:
    """`-h`/`--help` must never reach the app's dispatch -- a printed-and-quit invocation
    stays that way rather than becoming resident."""
    with pytest.raises(SystemExit):
        parse(["--help"])


def test_unknown_subcommand_exits_rather_than_silently_falling_through() -> None:
    with pytest.raises(SystemExit):
        parse(["frobnicate"])
