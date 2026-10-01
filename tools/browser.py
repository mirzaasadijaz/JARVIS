"""browser-use / Playwright wrapper tools — skip this whole file if you
connect the official Playwright MCP server instead (see the Tech Stack
Guide, "Built-in tools vs. tools you build yourself").

Keeps one persistent browser page across tool calls within a run, so
"go to X" then "click the login button" refers to the same page.
"""

from langchain_core.tools import tool
from playwright.sync_api import sync_playwright

_playwright = None
_browser = None
_page = None


def _get_page():
    global _playwright, _browser, _page
    if _page is None:
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(headless=True)
        _page = _browser.new_page()
    return _page


@tool
def browser_navigate(url: str) -> str:
    """Navigate the browser to a URL."""
    _get_page().goto(url, wait_until="domcontentloaded")
    return f"Navigated to {url}"


@tool
def browser_click(selector: str) -> str:
    """Click an element on the current page, identified by a CSS selector or text.

    Args:
        selector: A CSS selector (e.g. "#submit-button") or visible text
            (Playwright's `text=` prefix also works here, e.g. "text=Log in")
    """
    _get_page().click(selector)
    return f"Clicked: {selector}"


@tool
def browser_type(selector: str, text: str) -> str:
    """Type text into an input field.

    Args:
        selector: CSS selector for the input field
        text: The text to type
    """
    _get_page().fill(selector, text)
    return f"Typed into {selector}: {text}"


@tool
def browser_get_text() -> str:
    """Get the visible text content of the current page."""
    return _get_page().inner_text("body")


@tool
def browser_get_html() -> str:
    """Get the full HTML of the current page."""
    return _get_page().content()


def close() -> None:
    """Call when shutting down — not an agent tool, just cleanup."""
    if _browser:
        _browser.close()
    if _playwright:
        _playwright.stop()
