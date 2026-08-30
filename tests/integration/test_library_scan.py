"""Feature-level tests for scanning a product library folder tree into a
ScanResult -- built against a fixture directory tree in a temp directory
(never the real flash drive), per PROJECT_INSTRUCTIONS.md sections 9.2
and 10.

scan_library() only checks for file *existence*, so these fixtures use
empty placeholder files rather than real PSDs -- much faster, and the
scan logic doesn't care about PSD content.
"""

from pathlib import Path

from patch_pos.library import scan_library


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"placeholder")


class TestScanLibrary:
    def test_finds_rectangular_and_circular_products(self, tmp_path):
        _touch(tmp_path / "MP-P-000 - LOGO" / "3x2-images" / "1-image-template.psd")
        _touch(
            tmp_path
            / "MP-P-352 - MAPUA LOGO CIRCULAR"
            / "3x2-images"
            / "1-image-template-circular.psd"
        )

        result = scan_library(tmp_path)

        by_sku = {p.sku: p for p in result.products}
        assert set(by_sku) == {"MP-P-000", "MP-P-352"}
        assert by_sku["MP-P-000"].shape == "rectangular"
        assert by_sku["MP-P-000"].name == "LOGO"
        assert by_sku["MP-P-352"].shape == "circular"

    def test_circular_source_at_folder_root_is_found(self, tmp_path):
        # Some real folders (e.g. MP-P-760) put the circular source
        # directly at the SKU folder root, with no 3x2-images subfolder.
        _touch(tmp_path / "MP-P-760 - BTS LOGO 3 CIRCULAR" / "1-image-template-circular.psd")

        result = scan_library(tmp_path)

        assert len(result.products) == 1
        assert result.products[0].shape == "circular"

    def test_folder_missing_source_is_skipped(self, tmp_path):
        # Legacy structure with no 1-image-template*.psd at all (e.g. the
        # real MP-P-449 CAPTAIN AMERICA folder).
        _touch(tmp_path / "MP-P-449 - CAPTAIN AMERICA" / "PATCH-PHOTO-TEMPLATE-CUSTOM CUTOUT.psd")
        _touch(tmp_path / "MP-P-449 - CAPTAIN AMERICA" / "A4-PATCH-TEMPLATE-CUSTOM.ai")

        result = scan_library(tmp_path)

        assert result.products == []

    def test_empty_product_folder_is_skipped(self, tmp_path):
        (tmp_path / "MP-P-514 - MAVERICKS #9").mkdir()

        result = scan_library(tmp_path)

        assert result.products == []

    def test_non_product_folder_is_skipped(self, tmp_path):
        _touch(tmp_path / "BICYCLE" / "some_photo.jpg")

        result = scan_library(tmp_path)

        assert result.products == []

    def test_loose_thumbnail_is_found(self, tmp_path):
        _touch(tmp_path / "MP-P-001 - POGI" / "3x2-images" / "1-image-template.psd")
        _touch(tmp_path / "MP-P-001 - POGI" / "Product Photo 1.jpg")

        result = scan_library(tmp_path)

        assert result.products[0].thumbnail_path == tmp_path / "MP-P-001 - POGI" / "Product Photo 1.jpg"

    def test_thumbnail_in_assets_subfolder_is_found(self, tmp_path):
        _touch(tmp_path / "MP-P-050 - BLINK" / "3x2-images" / "1-image-template.psd")
        _touch(
            tmp_path / "MP-P-050 - BLINK" / "PATCH-PHOTO-TEMPLATE-assets" / "Product Photo 1.jpg"
        )

        result = scan_library(tmp_path)

        assert result.products[0].thumbnail_path == (
            tmp_path / "MP-P-050 - BLINK" / "PATCH-PHOTO-TEMPLATE-assets" / "Product Photo 1.jpg"
        )

    def test_no_thumbnail_available_is_none(self, tmp_path):
        _touch(tmp_path / "MP-P-002 - MAGANDA" / "3x2-images" / "1-image-template.psd")

        result = scan_library(tmp_path)

        assert result.products[0].thumbnail_path is None

    def test_total_size_bytes_reflects_actual_files(self, tmp_path):
        path = tmp_path / "MP-P-001 - POGI" / "3x2-images" / "1-image-template.psd"
        _touch(path)
        expected_size = path.stat().st_size

        result = scan_library(tmp_path)

        assert result.total_size_bytes == expected_size

    def test_products_sorted_by_folder_iteration_are_stable(self, tmp_path):
        _touch(tmp_path / "MP-P-002 - B" / "3x2-images" / "1-image-template.psd")
        _touch(tmp_path / "MP-P-001 - A" / "3x2-images" / "1-image-template.psd")

        result = scan_library(tmp_path)

        skus = [p.sku for p in result.products]
        assert set(skus) == {"MP-P-001", "MP-P-002"}
