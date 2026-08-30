"""Unit tests for the pywebview Api bridge, using a fake window object
instead of a real GUI window -- see PROJECT_INSTRUCTIONS.md section 9.3.
"""

import webview

from patch_pos.app import Api


class _FakeWindow:
    def __init__(self, dialog_result):
        self.dialog_result = dialog_result
        self.calls = []

    def create_file_dialog(self, dialog_type, **kwargs):
        self.calls.append((dialog_type, kwargs))
        return self.dialog_result


class TestSelectLibraryFolder:
    def test_returns_selected_path(self):
        api = Api()
        api.window = _FakeWindow(dialog_result=("/Volumes/MP-JLS/MNP Patch Master List",))

        assert api.select_library_folder() == "/Volumes/MP-JLS/MNP Patch Master List"
        assert api.window.calls == [(webview.FileDialog.FOLDER, {})]

    def test_returns_none_when_dialog_cancelled(self):
        api = Api()
        api.window = _FakeWindow(dialog_result=None)

        assert api.select_library_folder() is None

    def test_returns_none_for_empty_result(self):
        api = Api()
        api.window = _FakeWindow(dialog_result=())

        assert api.select_library_folder() is None


class TestSelectPdfSavePath:
    def test_returns_full_path_when_dialog_returns_a_plain_string(self):
        # pywebview's real macOS Cocoa backend returns a plain string for
        # SAVE dialogs (NSSavePanel.filename()), unlike FOLDER/OPEN
        # dialogs which return a tuple. Indexing [0] on that string
        # silently returned just its first character ('/') instead of
        # the path -- this is exactly the bug a real user hit in
        # production (a FileExistsError "File exists: '/'" from
        # reportlab trying to write to the root of the filesystem).
        api = Api()
        api.window = _FakeWindow(dialog_result="/Users/x/Desktop/print_sheet.pdf")

        result = api.select_pdf_save_path("print_sheet.pdf")

        assert result == "/Users/x/Desktop/print_sheet.pdf"

    def test_returns_selected_path_when_dialog_returns_a_tuple(self):
        # Some pywebview backends (or future versions) may return a
        # tuple instead -- both shapes must work.
        api = Api()
        api.window = _FakeWindow(dialog_result=("/Users/x/Desktop/print_sheet.pdf",))

        result = api.select_pdf_save_path("print_sheet.pdf")

        assert result == "/Users/x/Desktop/print_sheet.pdf"
        dialog_type, kwargs = api.window.calls[0]
        assert dialog_type == webview.FileDialog.SAVE
        assert kwargs["save_filename"] == "print_sheet.pdf"

    def test_returns_none_when_dialog_cancelled(self):
        api = Api()
        api.window = _FakeWindow(dialog_result=None)

        assert api.select_pdf_save_path("print_sheet.pdf") is None

    def test_no_default_output_folder_is_prefilled(self):
        # Every save prompts fresh -- see PROJECT_INSTRUCTIONS.md section
        # 5, point 7 ("blank save dialog every time"). The dialog call
        # must never pass a `directory` kwarg.
        api = Api()
        api.window = _FakeWindow(dialog_result=("/tmp/out.pdf",))

        api.select_pdf_save_path("print_sheet.pdf")

        _dialog_type, kwargs = api.window.calls[0]
        assert "directory" not in kwargs
