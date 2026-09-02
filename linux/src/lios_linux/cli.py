"""Parsing this application's command-line entry points.

Every subcommand here is also invocable by name from any desktop's own keybinding settings,
independent of the GlobalShortcuts portal -- `lios send-clipboard` and `lios send-file` are
the exported CLI fallback the architecture calls for (the design). A second invocation's argv
is forwarded to the running primary instance by `Gio.Application`
(`G_APPLICATION_HANDLES_COMMAND_LINE`) and parsed again there, in `app.py`'s
`do_command_line`; this module only defines the grammar, with no application object in scope,
so it is fully unit-testable without a display.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class SendClipboard:
    """`lios send-clipboard` -- read the clipboard by priority and send it."""


@dataclass(frozen=True)
class SendFile:
    """`lios send-file [PATH]` -- send a specific file, or open a chooser if none given."""

    path: str | None


@dataclass(frozen=True)
class Pair:
    """`lios pair [URI]` -- redeem a pairing URI, typed or passed as an argument."""

    uri: str | None


@dataclass(frozen=True)
class ShowWindow:
    """No subcommand, or `lios show` -- just raise the window."""


Command = SendClipboard | SendFile | Pair | ShowWindow


def parse(argv: list[str]) -> Command:
    """Parse the arguments after the program name into one `Command`.

    Raises:
        SystemExit: `argv` does not match any known subcommand -- argparse's own behaviour,
            which also prints usage to stderr.
    """
    parser = argparse.ArgumentParser(prog="lios", add_help=True)
    subparsers = parser.add_subparsers(dest="subcommand")

    subparsers.add_parser("send-clipboard", help="Send the current clipboard to a paired phone")

    send_file_parser = subparsers.add_parser("send-file", help="Send a file to a paired phone")
    send_file_parser.add_argument(
        "path", nargs="?", default=None, help="File to send; omitted opens a file chooser"
    )

    pair_parser = subparsers.add_parser("pair", help="Redeem a pairing URI scanned or typed in")
    pair_parser.add_argument("uri", nargs="?", default=None, help="A lios://pair/... URI")

    subparsers.add_parser("show", help="Show the LIOS window")

    args = parser.parse_args(argv)

    if args.subcommand == "send-clipboard":
        return SendClipboard()
    if args.subcommand == "send-file":
        return SendFile(path=args.path)
    if args.subcommand == "pair":
        return Pair(uri=args.uri)
    return ShowWindow()
