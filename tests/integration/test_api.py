"""Feature-level tests for the full Api wiring -- library scan through
search, order, and print sheet generation -- against a fake window and a
fixture 'drive' built from the small fixture PSDs (never the production
template/library), per PROJECT_INSTRUCTIONS.md sections 9.2 and 10.
"""

import pymupdf
import pytest

from patch_pos.app import Api

from ..fixtures.build_drive import build_fixture_drive


class _FakeWindow:
    def __init__(self, save_path: str | None):
        self.save_path = save_path

    def create_file_dialog(self, dialog_type, **kwargs):
        return (self.save_path,) if self.save_path else None


@pytest.fixture
def api(tmp_path) -> Api:
    api = Api()
    api.window = _FakeWindow(save_path=None)
    library_root = build_fixture_drive(tmp_path)
    result = api.rescan_library(str(library_root))
    assert result["ok"] is True
    return api


class TestRescanAndSearch:
    def test_rescan_reports_products_and_shapes(self, api):
        info = api.get_library_info()
        assert info["ok"] is True
        assert info["total_products"] == 4

    def test_search_finds_by_partial_name(self, api):
        result = api.search_products(query="red")
        assert result["ok"] is True
        assert result["total"] == 1
        assert result["products"][0]["sku"] == "MP-P-001"

    def test_disk_usage_reports_something(self, api):
        result = api.get_disk_usage()
        assert result["ok"] is True
        assert result["total_bytes"] > 0


class TestSearchShapeFilter:
    def test_shape_filter_excludes_other_shape(self, api):
        result = api.search_products(shape="rectangular")
        assert result["total"] == 2  # RED and BLUE, not the circular one

    def test_no_shape_filter_returns_everything(self, api):
        result = api.search_products(shape=None)
        assert result["total"] == 4


class TestThumbnails:
    def test_no_jpg_falls_back_to_flattened_psd(self, api):
        products = api.search_products(query="RED")["products"]
        result = api.get_thumbnail(products[0]["folder_path"])
        assert result["ok"] is True
        assert result["data_url"].startswith("data:image/png;base64,")

    def test_batch_fetches_multiple_at_once(self, api):
        products = api.search_products(shape=None)["products"]
        paths = [p["folder_path"] for p in products]

        result = api.get_thumbnails(paths)

        assert result["ok"] is True
        assert set(result["thumbnails"]) == set(paths)
        for data_url in result["thumbnails"].values():
            assert data_url.startswith("data:image/")

    def test_batch_silently_skips_unknown_paths(self, api):
        result = api.get_thumbnails(["/nonexistent/path"])
        assert result["ok"] is True
        assert result["thumbnails"] == {}


class TestOrderFlow:
    def test_add_search_result_to_order_updates_summary(self, api):
        api.set_order_template("rectangular")
        red = api.search_products(query="RED")["products"][0]

        result = api.add_to_order(red["folder_path"], quantity=2)

        assert result["ok"] is True
        assert result["total_items"] == 2
        assert result["cap"] == 2  # mini_template fixture has 2 rect slots
        assert result["over_cap"] is False

    def test_adding_mismatched_shape_returns_error_not_exception(self, api):
        # Order.add() must guard against this even though the frontend is
        # expected to filter the grid by the order's template (tested in
        # TestSearchShapeFilter below) -- defense in depth against a
        # stale grid or a direct Api call.
        api.set_order_template("rectangular")
        circular = api.search_products(query="YELLOW", shape=None)["products"][0]

        result = api.add_to_order(circular["folder_path"])

        assert result["ok"] is False
        assert "circular" in result["error"] or "rectangular" in result["error"]

    def test_quantity_over_cap_is_flagged(self, api):
        api.set_order_template("rectangular")
        red = api.search_products(query="RED")["products"][0]

        result = api.add_to_order(red["folder_path"], quantity=3)  # cap is 2

        assert result["ok"] is True
        assert result["over_cap"] is True

    def test_remove_and_clear(self, api):
        api.set_order_template("rectangular")
        red = api.search_products(query="RED")["products"][0]
        api.add_to_order(red["folder_path"])

        api.remove_from_order(red["folder_path"])
        assert api.get_order()["total_items"] == 0

        api.add_to_order(red["folder_path"])
        api.clear_order()
        assert api.get_order()["total_items"] == 0
        assert api.get_order()["template_shape"] is None


class TestGeneratePrintSheet:
    def test_generates_valid_pdf_and_clears_order(self, api, tmp_path):
        api.set_order_template("rectangular")
        red = api.search_products(query="RED")["products"][0]
        blue = api.search_products(query="BLUE")["products"][0]
        api.add_to_order(red["folder_path"])
        api.add_to_order(blue["folder_path"])

        output_path = tmp_path / "output.pdf"
        api.window.save_path = str(output_path)

        result = api.generate_print_sheet()

        assert result["ok"] is True
        assert result["slots_used"] == 2
        assert output_path.exists()

        doc = pymupdf.open(output_path)
        assert doc.page_count == 1
        doc.close()

        assert api.get_order()["total_items"] == 0  # cleared after success

    def test_over_cap_returns_error_and_writes_no_file(self, api, tmp_path):
        api.set_order_template("rectangular")
        red = api.search_products(query="RED")["products"][0]
        api.add_to_order(red["folder_path"], quantity=3)  # cap is 2

        output_path = tmp_path / "should_not_exist.pdf"
        api.window.save_path = str(output_path)

        result = api.generate_print_sheet()

        assert result["ok"] is False
        assert not output_path.exists()

    def test_cancelled_save_dialog_does_not_clear_order(self, api):
        api.set_order_template("rectangular")
        red = api.search_products(query="RED")["products"][0]
        api.add_to_order(red["folder_path"])
        api.window.save_path = None  # simulate Cancel

        result = api.generate_print_sheet()

        assert result["ok"] is True
        assert result["cancelled"] is True
        assert api.get_order()["total_items"] == 1  # untouched

    def test_empty_order_returns_error(self, api):
        api.set_order_template("rectangular")
        result = api.generate_print_sheet()
        assert result["ok"] is False
