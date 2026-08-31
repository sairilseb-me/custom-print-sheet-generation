"""E2E tests driving the real frontend through the full workflow: launch
-> scan library -> search -> add products to order -> pick template ->
generate print sheet -> confirm save dialog invoked with a correct file
-> confirm output PDF exists and is valid. Per PROJECT_INSTRUCTIONS.md
section 9.3: one rectangular flow, one circular flow, one over-cap error
flow.
"""

import pymupdf
from psd_tools import PSDImage

from ..fixtures.build_drive import build_fixture_drive


def _load_library(page, scripted_window, tmp_path):
    library_root = build_fixture_drive(tmp_path)
    scripted_window.library_folder_result = str(library_root)
    page.click("#select-library-btn")
    page.wait_for_selector("#app-view:not([hidden])")


def _add_product_to_order(page, sku: str):
    card = page.locator(".product-card", has_text=sku)
    card.locator("button").click()


class TestRectangularFlow:
    def test_launch_through_generate_and_verify_pdf(self, page, scripted_window, tmp_path):
        _load_library(page, scripted_window, tmp_path)

        page.click('.template-btn[data-shape="rectangular"]')
        page.wait_for_selector('.template-btn[data-shape="rectangular"].active')

        page.fill("#search-input", "RED")
        page.wait_for_timeout(400)  # debounce
        _add_product_to_order(page, "MP-P-001")

        page.wait_for_selector(".order-line")
        assert "MP-P-001" in page.text_content("#order-lines")
        assert "1 / 2 slots" in page.text_content("#order-total")

        output_path = tmp_path / "rect_output.pdf"
        scripted_window.save_path_result = str(output_path)
        page.click("#generate-btn")

        page.wait_for_selector("#success-banner:not([hidden])")
        assert "Saved to" in page.text_content("#success-banner")
        assert output_path.exists()

        doc = pymupdf.open(output_path)
        assert doc.page_count == 1
        doc.close()

        # Order clears after a successful generate.
        page.wait_for_selector("#order-total")
        assert "0" in page.text_content("#order-total").split("/")[0]


class TestCircularFlow:
    def test_launch_through_generate_and_verify_pdf(self, page, scripted_window, tmp_path):
        _load_library(page, scripted_window, tmp_path)

        page.click('.template-btn[data-shape="circular"]')
        page.wait_for_selector('.template-btn[data-shape="circular"].active')

        page.fill("#search-input", "YELLOW")
        page.wait_for_timeout(400)
        _add_product_to_order(page, "MP-P-003")

        page.wait_for_selector(".order-line")
        assert "1 / 2 slots" in page.text_content("#order-total")

        output_path = tmp_path / "circular_output.pdf"
        scripted_window.save_path_result = str(output_path)
        page.click("#generate-btn")

        page.wait_for_selector("#success-banner:not([hidden])")
        assert output_path.exists()

        doc = pymupdf.open(output_path)
        assert doc.page_count == 1
        doc.close()


class TestExportEditablePsdFlow:
    """The manual-editing alternative to Generate Print Sheet -- see
    psd_export.py. One flow suffices here since TestRectangularFlow /
    TestCircularFlow above already cover the shared add-to-order path."""

    def test_launch_through_export_and_verify_psd(self, page, scripted_window, tmp_path):
        _load_library(page, scripted_window, tmp_path)

        page.click('.template-btn[data-shape="rectangular"]')
        page.wait_for_selector('.template-btn[data-shape="rectangular"].active')

        page.fill("#search-input", "RED")
        page.wait_for_timeout(400)  # debounce
        _add_product_to_order(page, "MP-P-001")

        page.wait_for_selector(".order-line")
        assert "1 / 2 slots" in page.text_content("#order-total")

        output_path = tmp_path / "rect_output.psd"
        scripted_window.save_path_result = str(output_path)
        page.click("#export-psd-btn")

        page.wait_for_selector("#success-banner:not([hidden])")
        assert "Saved to" in page.text_content("#success-banner")
        assert output_path.exists()

        layer_names = {layer.name for layer in PSDImage.open(output_path)}
        assert layer_names == {"Background", "Guides", "1-image-template"}

        # Order clears after a successful export, same as generate.
        page.wait_for_selector("#order-total")
        assert "0" in page.text_content("#order-total").split("/")[0]


class TestOverCapFlow:
    def test_over_cap_disables_generate_and_backend_rejects_it(self, page, scripted_window, tmp_path):
        _load_library(page, scripted_window, tmp_path)

        page.click('.template-btn[data-shape="rectangular"]')
        page.wait_for_selector('.template-btn[data-shape="rectangular"].active')

        page.fill("#search-input", "RED")
        page.wait_for_timeout(400)
        _add_product_to_order(page, "MP-P-001")  # quantity 1
        page.wait_for_selector(".order-line")

        # Push quantity to 3, one over the fixture template's 2-slot cap.
        page.click('.order-line [data-action="inc"]')
        page.click('.order-line [data-action="inc"]')

        page.wait_for_selector("text=3 / 2 slots")
        assert page.is_disabled("#generate-btn")  # UI blocks an over-cap generate

        # Defense in depth: the backend must independently reject it too,
        # not just rely on the disabled button.
        output_path = tmp_path / "should_not_exist.pdf"
        scripted_window.save_path_result = str(output_path)
        result = page.evaluate("() => window.pywebview.api.generate_print_sheet()")

        assert result["ok"] is False
        assert not output_path.exists()
