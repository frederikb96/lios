# lios-linux

The Linux half of LIOS: a resident GTK4 + libadwaita application (PyGObject) with one window,
holding a WebSocket to the relay and running under GNOME's Background Apps with no window
open. Sending is a paste into that window; receiving is a notification whose click opens the
window with the new item selected, ready to copy or save. Shipped as a Flatpak.

## Clipboard

GNOME implements no clipboard protocol usable by a background or sandboxed client
(`wlr-data-control` and `ext-data-control` are refused by mutter; the Clipboard portal only
extends RemoteDesktop/InputCapture sessions). A resident GTK app's own `Gdk.Clipboard` writes
natively only from a genuine in-window input event -- mutter requires both keyboard focus and
a `wl_display` serial newer than the current owner's, and GDK sources that serial only from a
key/button press the application itself received. So every clipboard touch here happens inside
this window, in response to an input event the app received: Ctrl+V to send, a Copy button (or
its accelerator) to receive. See `src/lios_linux/clipboard/` for the mechanism, and
`src/lios_linux/clipboard/priority.py` for the ordered mime-type priority that decides what a
paste or a drop actually is.

There is no clipboard-change monitoring, and never will be on GNOME: `wl-paste --watch`
refuses to run at all, since it needs a data-control protocol mutter does not implement.
Sending is always a deliberate act -- a paste, a drop, typed text, a chosen file -- never a
background mirror.

The clipboard is owned by whichever process last set it; if this app exits (or is replaced as
owner by something else) before a paste, the content is gone. Normal Wayland behaviour, not a
bug.

## Staying resident

`self.hold()` at startup keeps the process running once its last window closes -- otherwise a
`Gtk.Application` quits the moment its window count reaches zero. Closing the window hides
it rather than destroying it, so reopening (via a notification click or the bound shortcut) is
instant and its scroll position and selection survive. A running, windowless, sandboxed app is
what GNOME lists under Background Apps in its system menu, with a quit button that needs no
code here to work.

There is no global shortcut portal call anywhere in this app. `lios show` is the one
command-line entry point, forwarded to the running instance over D-Bus by
`Gio.Application`'s command-line handling -- any desktop's own keyboard settings can bind it
directly, with no portal, no consent dialog, and no dependency on a GNOME version that has one.

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
`org.gnome.Platform` plus this app's own Python dependencies -- no other binary, so the
whole bundle stays MIT.

```
flatpak-builder --user --install --force-clean build packaging/io.github.frederikb96.Lios.yml
```

A single-file, installable bundle (for handing to someone without `flatpak-builder`, or
syncing to another machine) needs an intermediate local repo rather than `--install`:

```
flatpak-builder --repo=repo --force-clean build packaging/io.github.frederikb96.Lios.yml
flatpak build-bundle --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
    repo lios.flatpak io.github.frederikb96.Lios
```

`--runtime-repo` embeds a pointer to Flathub's `.flatpakrepo` in the bundle, so `flatpak
install --user --bundle lios.flatpak` on a machine with no Flathub remote configured yet gets
offered one automatically to pull `org.gnome.Platform`//50 from, rather than failing on a
missing runtime with no next step.

`share/dbus-1/services/io.github.frederikb96.Lios.service` (installed by `lios-linux`'s own
build commands in the manifest) is required, not automatic, for the `.desktop` file's
`DBusActivatable=true` -- `flatpak-builder`'s plain `--install` build does not validate this,
but exporting to a repo (`--repo=`, which `build-bundle` needs) does, and fails the export
without it (`Desktop file D-Bus activatable, but service file not exported`).

## Gotchas

`Adw.StatusPage` (and other `Adw` widgets marked final in libadwaita) cannot be subclassed
from PyGObject -- doing so raises `RuntimeError: could not create new GType` at class
definition time, not at first use. Compose one as a child widget instead (`ui/onboarding.py`
holds a `.widget` rather than inheriting from `Adw.StatusPage`).

## Layout

- `clipboard/` -- native `Gdk.Clipboard` writes, and the ordered mime-type priority that
  decides what a paste or a drop actually is.
- `history/` -- SQLite metadata plus a sibling blob directory, with explicit retention.
- `relaylink/` -- the relay connection: REST calls, the `/api/stream` WebSocket with
  reconnect/backoff, pairing, and the item envelope (framing + encryption, via
  `lios-protocol`).
- `portals/` -- Background (autostart) and Notification.
- `keyring.py` -- the device token and group key, via the Secret Service.
- `ui/` -- the window (paste-to-send, drag-and-drop, the history list with its Copy/Save
  actions), preferences, pairing view, and history rows.
- `cli.py` / `app.py` -- the command-line grammar and the `Gtk.Application` that ties
  everything together, held resident from startup.
