"""pywebview shell: a native desktop window rendering the HTML/CSS/JS
frontend, with a thin `Api` bridge exposed to the frontend as
`pywebview.api.*` for native folder-select and save-file dialogs.

`Api` doesn't reach for the global `webview.windows[0]` -- its window is
injected via the `.window` attribute after creation, so dialog logic can
be unit tested against a fake window object without a real GUI (see
PROJECT_INSTRUCTIONS.md section 9.3 on mocking the js_api bridge).
"""

from pathlib import Path

import webview

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
DEFAULT_WINDOW_SIZE = (1200, 800)
MIN_WINDOW_SIZE = (900, 600)


class Api:
    def __init__(self) -> None:
        self.window: webview.Window | None = None

    def select_library_folder(self) -> str | None:
        """Native folder picker -- used for 'Rescan Library' and picking
        an external library path, per PROJECT_INSTRUCTIONS.md section 4.
        """
        results = self.window.create_file_dialog(webview.FileDialog.FOLDER)
        return results[0] if results else None

    def select_pdf_save_path(self, default_filename: str = "print_sheet.pdf") -> str | None:
        """Native save dialog with no pre-filled default path -- every
        'Generate Print Sheet' click prompts fresh, per
        PROJECT_INSTRUCTIONS.md section 5, point 7 ("blank save dialog
        every time")."""
        results = self.window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=default_filename,
            file_types=("PDF Files (*.pdf)",),
        )
        return results[0] if results else None


def create_app_window(api: Api | None = None) -> webview.Window:
    api = api or Api()
    window = webview.create_window(
        "Print Sheet POS",
        url=str(FRONTEND_DIR / "index.html"),
        js_api=api,
        width=DEFAULT_WINDOW_SIZE[0],
        height=DEFAULT_WINDOW_SIZE[1],
        min_size=MIN_WINDOW_SIZE,
    )
    api.window = window
    return window


def main() -> None:
    create_app_window()
    webview.start()


if __name__ == "__main__":
    main()
