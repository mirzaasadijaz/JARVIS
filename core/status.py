"""System tray status indicator — listening / thinking / speaking.

Honest caveat: like tools/desktop.py, this can't be functionally tested
here — pystray needs a real GTK/Win32/Cocoa backend depending on your
OS, none of which exist in this sandbox (confirmed: it fails with
"Namespace Gtk not available" when imported here). Written to pystray's
documented API; verify on your actual machine.
"""

import threading

import pystray
from PIL import Image, ImageDraw

_COLORS = {
    "idle": (128, 128, 128),
    "listening": (46, 204, 113),
    "thinking": (241, 196, 15),
    "speaking": (52, 152, 219),
}

_icon: pystray.Icon | None = None


def _make_image(color: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, 56, 56), fill=color)
    return img


def set_status(state: str) -> None:
    """Call this from voice/loop.py (or anywhere) to update the tray icon:
        set_status("listening")   # while waiting for speech
        set_status("thinking")    # while the agent is reasoning/calling tools
        set_status("speaking")    # while TTS is playing back
        set_status("idle")        # default
    """
    if _icon is not None:
        _icon.icon = _make_image(_COLORS.get(state, _COLORS["idle"]))
        _icon.title = f"Jarvis — {state}"


def run_with_status(target_fn) -> None:
    """Runs `target_fn` (e.g. voice.loop.run) in a background thread while
    the tray icon's event loop owns the main thread — pystray's required
    pattern, since .run() blocks."""
    global _icon

    def _setup(icon: pystray.Icon) -> None:
        icon.visible = True
        threading.Thread(target=target_fn, daemon=True).start()

    menu = pystray.Menu(pystray.MenuItem("Quit", lambda: _icon.stop()))
    _icon = pystray.Icon("jarvis", _make_image(_COLORS["idle"]), "Jarvis", menu)
    _icon.run(setup=_setup)
