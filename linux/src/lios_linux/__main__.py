"""Entry point: the installed `lios` console script, and `python -m lios_linux`."""

from __future__ import annotations

import sys


def main() -> int:
    """Run the resident application. A second invocation's argv reaches the same process
    through `Gio.Application`'s command-line forwarding -- see `app.py`'s `do_command_line`."""
    from lios_linux.app import LiosApplication

    app = LiosApplication()
    return int(app.run(sys.argv))


if __name__ == "__main__":
    raise SystemExit(main())
