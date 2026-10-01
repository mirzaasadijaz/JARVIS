"""PIN entry — a small tkinter popup window, blocks until the correct
PIN is entered or the window is closed.

Honest caveat: like tools/desktop.py and core/status.py, this needs a
real display and couldn't be visually verified in the sandbox this was
built in (confirmed: tkinter itself isn't even installed there by
default). tkinter ships with standard Python on Windows, so this should
just work without any extra install on your machine.
"""

import tkinter as tk

from config import settings


def prompt_for_pin() -> bool:
    """Opens a PIN entry window in front of everything else. Returns
    True if the correct PIN was entered, False if it was wrong or the
    window was closed without submitting."""
    settings.require("jarvis_pin")
    result = {"correct": False}

    def submit() -> None:
        result["correct"] = entry.get() == settings.jarvis_pin
        root.destroy()

    root = tk.Tk()
    root.title("Jarvis")
    root.geometry("280x130")
    root.attributes("-topmost", True)

    tk.Label(root, text="Enter PIN to unlock Jarvis:").pack(pady=(15, 5))
    entry = tk.Entry(root, show="*", justify="center")
    entry.pack()
    entry.focus_set()
    entry.bind("<Return>", lambda _event: submit())

    tk.Button(root, text="Unlock", command=submit).pack(pady=10)

    root.mainloop()
    return result["correct"]
