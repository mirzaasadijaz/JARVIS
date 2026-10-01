"""@tool take_screenshot, click_at, type_text, press_key, open_application, clipboard.

Desktop automation tools. Register HumanInTheLoopMiddleware around the
ones capable of real damage (see core/middleware.py) before wiring these
into the agent for real use.
"""

import base64
import io
import subprocess

import mss
import pyautogui
import pyperclip
from langchain_core.tools import tool

pyautogui.FAILSAFE = True  # moving the mouse to a screen corner aborts — keep this on


@tool
def take_screenshot() -> str:
    """Capture the current screen. Returns a base64-encoded PNG."""
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])  # monitors[0] is "all monitors combined"
        img_bytes = mss.tools.to_png(shot.rgb, shot.size)
    return base64.b64encode(img_bytes).decode("utf-8")


@tool
def click_at(x: int, y: int) -> str:
    """Move the mouse to (x, y) and left-click."""
    pyautogui.click(x, y)
    return f"Clicked at ({x}, {y})"


@tool
def type_text(text: str) -> str:
    """Type text at the current cursor/focus position."""
    pyautogui.write(text, interval=0.02)
    return f"Typed: {text}"


@tool
def press_key(key: str) -> str:
    """Press a single key or key combination, e.g. "enter", "ctrl+c"."""
    if "+" in key:
        pyautogui.hotkey(*key.split("+"))
    else:
        pyautogui.press(key)
    return f"Pressed: {key}"


@tool
def open_application(name: str) -> str:
    """Launch an application by name (must be on PATH, or a full path)."""
    subprocess.Popen(name, shell=True)
    return f"Launched: {name}"


@tool
def read_clipboard() -> str:
    """Read the current contents of the system clipboard."""
    return pyperclip.paste()


@tool
def write_clipboard(text: str) -> str:
    """Write text to the system clipboard."""
    pyperclip.copy(text)
    return "Clipboard updated"
