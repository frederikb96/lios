# lios-linux

The Linux half of LIOS: a resident GTK4 + libadwaita application (PyGObject) that holds a
WebSocket to the relay, raises a desktop notification when something arrives from a paired
phone, and sends the clipboard (or a file, or typed text) the other way. Shipped as a Flatpak.

## Clipboard

GNOME implements no clipboard protocol usable by a background or sandboxed client
(`wlr-data-control` and `ext-data-control` are refused by mutter; the Clipboard portal only
extends RemoteDesktop/InputCapture sessions). This app instead spawns `wl-copy`/`wl-paste` --
which work by briefly presenting a transparent surface and taking focus with a fresh input
serial -- for every clipboard read and write. A resident GTK app's own `Gdk.Clipboard` can
write natively only from a genuine in-window button click, which has a fresh serial of its
own; it cannot do so from a global-shortcut or notification trigger, because GNOME's focus and
serial checks are satisfied only by that fresh input event, and an activation token buys focus
but not a serial. See `src/lios_linux/clipboard/` for the split.

Every clipboard touch briefly steals focus. This app only ever touches the clipboard on an
explicit user action -- a shortcut press, a notification click, a button -- never on a timer or
in a loop, and there is no clipboard-change monitoring: `wl-paste --watch` refuses to run on
GNOME at all.

The clipboard is owned by whichever process last set it; if this app exits (or is replaced as
owner by something else) before a paste, the content is gone. Normal Wayland behaviour, not a
bug.

## Development

```
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src/ tests/
mypy src/
```

`--system-site-packages` is required: PyGObject's `gi` bindings for GTK4/libadwaita/libsoup3
come from the distro (`gir1.2-gtk-4.0`, `gir1.2-adw-1`, `gir1.2-soup-3.0`, `gir1.2-secret-1`),
not from PyPI.

## Packaging

`packaging/io.github.frederikb96.Lios.yml` is the Flatpak manifest, building against
`org.gnome.Platform` and bundling `wl-clipboard` from source. `wl-clipboard` is
GPL-3.0-or-later and is called as a subprocess -- aggregation, not linking, so this
application stays MIT. The manifest builds wl-clipboard from source, which satisfies the
source-offer obligation.

```
flatpak-builder --user --install --force-clean build packaging/io.github.frederikb96.Lios.yml
```

## Layout

- `clipboard/` -- `wl-copy`/`wl-paste` and native `Gdk.Clipboard`, and the ordered mime-type
  priority that decides which to read.
- `history/` -- SQLite metadata plus a sibling blob directory, with explicit retention.
- `relaylink/` -- the relay connection: REST calls, the `/api/stream` WebSocket with
  reconnect/backoff, pairing, and the item envelope (framing + encryption, via
  `lios-protocol`).
- `portals/` -- Background (autostart), GlobalShortcuts, and Notification.
- `keyring.py` -- the device token and group key, via the Secret Service.
- `ui/` -- the window, preferences, pairing view, and history rows.
- `cli.py` / `app.py` -- the command-line grammar and the `Gtk.Application` that ties
  everything together.
