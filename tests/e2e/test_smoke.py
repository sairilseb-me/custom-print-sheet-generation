"""Harness smoke test -- confirms the page loads and the bridge to the
real Api is wired correctly, before the full flow tests below rely on it.
"""

from ..fixtures.build_drive import build_fixture_drive


def test_page_loads_and_select_library_flow_works(page, scripted_window, tmp_path):
    assert page.title() == "Print Sheet POS"
    assert page.is_hidden("#app-view")

    library_root = build_fixture_drive(tmp_path)
    scripted_window.library_folder_result = str(library_root)

    page.click("#select-library-btn")
    page.wait_for_selector("#app-view:not([hidden])")

    assert "4 products in library" in page.text_content("#library-summary")
