"""Feature-level tests for the full pipeline: parse a real (fixture) PSD
template, flatten real (fixture) source PSDs, composite, export a PDF,
then re-open that PDF and verify it -- not just "a file was created".
See PROJECT_INSTRUCTIONS.md section 9.2.

These run against fixture files only, never the real flash drive/product
library/output folder (section 9.2, section 10).
"""

from pathlib import Path

import pymupdf
import pytest
from psd_tools import PSDImage

from patch_pos.compositor import composite_sheet, flatten_source_psd
from patch_pos.errors import SlotCapExceededError
from patch_pos.pdf_export import export_pdf
from patch_pos.slots import get_layout, load_template_layouts

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def template_layouts():
    psd = PSDImage.open(FIXTURES_DIR / "mini_template.psd")
    return load_template_layouts(psd)


def _rasterize_first_page(pdf_path: Path, dpi: int = 300):
    doc = pymupdf.open(pdf_path)
    try:
        assert doc.page_count == 1
        page = doc[0]
        # Rasterize at the same dpi used for export_pdf() so 1 raster
        # pixel == 1 original canvas pixel, keeping slot coordinates
        # directly comparable.
        pix = page.get_pixmap(dpi=dpi)
        return pix, page.rect
    finally:
        doc.close()


class TestRectangularFlow:
    def test_generates_pdf_with_products_in_expected_positions(self, template_layouts, tmp_path):
        layout = get_layout(template_layouts, "rectangular")
        images = [
            flatten_source_psd(FIXTURES_DIR / "source_red.psd"),
            flatten_source_psd(FIXTURES_DIR / "source_blue.psd"),
        ]

        sheet = composite_sheet(layout, images)
        output_path = tmp_path / "rect_output.pdf"
        export_pdf(sheet, output_path, dpi=300)

        assert output_path.exists()
        pix, page_rect = _rasterize_first_page(output_path)

        # Page size in points should match the 300dpi->pt conversion of the fixture canvas.
        expected_width_pt = 400 * 72.0 / 300
        expected_height_pt = 300 * 72.0 / 300
        assert page_rect.width == pytest.approx(expected_width_pt, abs=0.5)
        assert page_rect.height == pytest.approx(expected_height_pt, abs=0.5)

        # Pixel regions: sample well inside each slot.
        assert pix.pixel(70, 50)[:3] == (255, 0, 0)  # slot 1 -> red
        assert pix.pixel(250, 50)[:3] == (0, 0, 255)  # slot 2 -> blue


class TestCircularFlow:
    def test_generates_pdf_with_products_in_expected_positions(self, template_layouts, tmp_path):
        layout = get_layout(template_layouts, "circular")
        images = [
            flatten_source_psd(FIXTURES_DIR / "source_yellow_circular.psd"),
            flatten_source_psd(FIXTURES_DIR / "source_purple_circular.psd"),
        ]

        sheet = composite_sheet(layout, images)
        output_path = tmp_path / "circular_output.pdf"
        export_pdf(sheet, output_path, dpi=300)

        pix, _ = _rasterize_first_page(output_path)
        assert pix.pixel(60, 160)[:3] == (230, 200, 0)  # slot 1 -> yellow
        assert pix.pixel(240, 160)[:3] == (150, 0, 200)  # slot 2 -> purple


class TestOverCapErrorFlow:
    def test_exceeding_cap_does_not_generate_a_pdf(self, template_layouts, tmp_path):
        layout = get_layout(template_layouts, "rectangular")  # 2-slot fixture layout
        images = [
            flatten_source_psd(FIXTURES_DIR / "source_red.psd"),
            flatten_source_psd(FIXTURES_DIR / "source_blue.psd"),
            flatten_source_psd(FIXTURES_DIR / "source_green.psd"),
        ]
        output_path = tmp_path / "should_not_exist.pdf"

        with pytest.raises(SlotCapExceededError):
            sheet = composite_sheet(layout, images)
            export_pdf(sheet, output_path)  # unreachable if check_cap did its job

        assert not output_path.exists()
