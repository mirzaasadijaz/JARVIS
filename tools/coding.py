"""@tool read_file, write_file, apply_patch — skip this whole file if
you use Claude's native text_editor tool instead (see the Tech Stack
Guide) — it does this more reliably than a hand-rolled diff/patch tool.
"""

import os

from langchain_core.tools import tool


@tool
def read_file(path: str) -> str:
    """Read and return the contents of a text file."""
    with open(path, encoding="utf-8") as f:
        return f.read()


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed.
    Overwrites the file if it already exists."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Wrote {len(content)} characters to {path}"


@tool
def apply_patch(path: str, old_text: str, new_text: str) -> str:
    """Replace one exact occurrence of old_text with new_text in a file.
    Fails if old_text doesn't appear exactly once, so a bad match can't
    silently corrupt the file.

    Args:
        path: File to edit
        old_text: Exact text to find (must appear exactly once)
        new_text: Text to replace it with
    """
    with open(path, encoding="utf-8") as f:
        content = f.read()

    count = content.count(old_text)
    if count == 0:
        return f"Error: text not found in {path}"
    if count > 1:
        return f"Error: text appears {count} times in {path} — must be unique"

    with open(path, "w", encoding="utf-8") as f:
        f.write(content.replace(old_text, new_text))
    return f"Patched {path}"
