"""Parsing this application's command-line entry points.

`lios` (or `lios show`, equivalently) is the entry point any desktop's own keybinding settings
bind to raise the resident app's window, focused and ready to paste. `lios background` is the
other resident-triggering command -- used only by the D-Bus service file and the autostart
command registered with the Background portal, both of which must bring the app up and keep it
running WITHOUT drawing a window; it never needs a user's own keybinding, so it is hidden from
`--help`. A second invocation's argv is forwarded to the running primary instance by
`Gio.Application` (`G_APPLICATION_HANDLES_COMMAND_LINE`) and parsed again there, in `app.py`'s
`do_command_line`; this module only defines the grammar, with no application object in scope,
so it is fully unit-testable without a display.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class Pair:
    """`lios pair [URI]` -- redeem a pairing URI, typed or passed as an argument."""

    uri: str | None


@dataclass(frozen=True)
class ShowWindow:
    """No subcommand, or `lios show` -- raise the window."""


@dataclass(frozen=True)
class RunBackground:
    """`lios background` -- come up and stay resident, drawing no window at all."""


Command = Pair | ShowWindow | RunBackground


def parse(argv: list[str]) -> Command:
    """Parse the arguments after the program name into one `Command`.

    Raises:
        SystemExit: `argv` does not match any known subcommand, or `-h`/`--help` was given --
            argparse's own behaviour, which also prints usage before exiting. Neither case
            reaches `app.py`'s dispatch, so a process invoked only to print and quit never
            becomes resident.
    """
    parser = argparse.ArgumentParser(prog="lios", add_help=True)
    subparsers = parser.add_subparsers(dest="subcommand")

    pair_parser = subparsers.add_parser("pair", help="Redeem a pairing URI scanned or typed in")
    pair_parser.add_argument("uri", nargs="?", default=None, help="A lios://pair/... URI")

    subparsers.add_parser("show", help="Show the LIOS window")

    # Internal: not something a user ever types or binds, so it stays out of --help.
    subparsers.add_parser("background", help=argparse.SUPPRESS)

    args = parser.parse_args(argv)

    if args.subcommand == "pair":
        return Pair(uri=args.uri)
    if args.subcommand == "background":
        return RunBackground()
    return ShowWindow()
