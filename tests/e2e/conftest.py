"""E2E fixtures: serve the real frontend/ over a local static HTTP
server and drive it in a real browser, with the Python backend calls
bound directly to a real `patch_pos.app.Api` instance through the same
`window.pywebview.api.*` bridge interface pywebview exposes -- per
PROJECT_INSTRUCTIONS.md section 9.3's decision to test this way instead
of automating the native pywebview window (more brittle to drive).

Uses the system-installed Chrome via Playwright's `channel="chrome"`
rather than Playwright's own bundled Chromium, since Playwright doesn't
ship browser binaries for this machine's OS version.
"""

import functools
import http.server
import threading
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from patch_pos.app import Api

FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"

API_METHODS = [
    "select_library_folder",
    "select_pdf_save_path",
    "rescan_library",
    "search_products",
    "get_thumbnail",
    "get_library_info",
    "get_disk_usage",
    "set_order_template",
    "add_to_order",
    "set_order_quantity",
    "remove_from_order",
    "clear_order",
    "get_order",
    "generate_print_sheet",
]


class ScriptedWindow:
    """Fake pywebview window backing the real Api under test -- each
    test sets the dialog return values it wants before triggering the
    action that opens them."""

    def __init__(self):
        self.library_folder_result: str | None = None
        self.save_path_result: str | None = None

    def create_file_dialog(self, dialog_type, **kwargs):
        import webview

        if dialog_type == webview.FileDialog.FOLDER:
            return (self.library_folder_result,) if self.library_folder_result else None
        if dialog_type == webview.FileDialog.SAVE:
            return (self.save_path_result,) if self.save_path_result else None
        return None


@pytest.fixture
def scripted_window() -> ScriptedWindow:
    return ScriptedWindow()


@pytest.fixture
def backend_api(scripted_window) -> Api:
    api = Api()
    api.window = scripted_window
    return api


@pytest.fixture(scope="session")
def frontend_server():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(FRONTEND_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


@pytest.fixture
def page(backend_api, frontend_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        browser_page = browser.new_page()

        for name in API_METHODS:
            bound_method = getattr(backend_api, name)
            browser_page.expose_function(f"__api_{name}", bound_method)

        bridge_script = "window.pywebview = { api: { " + ", ".join(
            f"{name}: (...args) => window.__api_{name}(...args)" for name in API_METHODS
        ) + " } };"
        browser_page.add_init_script(bridge_script)

        browser_page.goto(f"{frontend_server}/index.html")
        browser_page.evaluate("window.dispatchEvent(new Event('pywebviewready'))")

        yield browser_page
        browser.close()
