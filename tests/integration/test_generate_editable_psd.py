"""Feature-level tests for the editable-PSD export path: parse a real
(fixture) PSD template, flatten real (fixture) source PSDs, write a
layered .psd via export_editable_psd, then re-open that file and verify
its layer structure and composited pixels -- not just "a file was
created". Mirrors test_generate_sheet.py's structure/coverage for the PDF
path. See PROJECT_INSTRUCTIONS.md section 9.2.
"""

from pathlib import Path

import pytest
from psd_tools import PSDImage

from patch_pos.compositor import flatten_source_psd
from patch_pos.errors import SlotCapExceededError
from patch_pos.psd_export import export_editable_psd
from patch_pos.slots import get_layout, load_template_layouts

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def template_layouts():
    psd = PSDImage.open(FIXTURES_DIR / "mini_template.psd")
    return load_template_layouts(psd)


class TestRectangularFlow:
    def test_writes_layered_psd_with_products_on_separate_layers(self, template_layouts, tmp_path):
        layout = get_layout(template_layouts, "rectangular")
        images = [
            flatten_source_psd(FIXTURES_DIR / "source_red.psd"),
            flatten_source_psd(FIXTURES_DIR / "source_blue.psd"),
        ]

        output_path = tmp_path / "rect_output.psd"
        export_editable_psd(layout, images, output_path)

        assert output_path.exists()
        result = PSDImage.open(output_path)
        assert result.size == (400, 300)

        layer_names = {layer.name for layer in result}
        assert layer_names == {"Background", "Guides", "1-image-template", "2-image-template"}

        # Each patch is its own separate, independently movable layer --
        # the whole point of this export path.
        by_name = {layer.name: layer for layer in result}
        assert by_name["1-image-template"].bbox != by_name["2-image-template"].bbox

        img = result.composite(ignore_preview=True)
        assert img.getpixel((70, 50))[:3] == (255, 0, 0)  # slot 1 -> red
        assert img.getpixel((250, 50))[:3] == (0, 0, 255)  # slot 2 -> blue
        assert img.getpixel((5, 5))[:3] == (255, 255, 255)  # outside any slot

    def test_partial_order_only_creates_layers_for_filled_slots(self, template_layouts, tmp_path):
        layout = get_layout(template_layouts, "rectangular")
        images = [flatten_source_psd(FIXTURES_DIR / "source_red.psd")]

        output_path = tmp_path / "partial_output.psd"
        export_editable_psd(layout, images, output_path)

        result = PSDImage.open(output_path)
        layer_names = {layer.name for layer in result}
        assert layer_names == {"Background", "Guides", "1-image-template"}


class TestCircularFlow:
    def test_writes_layered_psd_with_products_on_separate_layers(self, template_layouts, tmp_path):
        layout = get_layout(template_layouts, "circular")
        images = [
            flatten_source_psd(FIXTURES_DIR / "source_yellow_circular.psd"),
            flatten_source_psd(FIXTURES_DIR / "source_purple_circular.psd"),
        ]

        output_path = tmp_path / "circular_output.psd"
        export_editable_psd(layout, images, output_path)

        result = PSDImage.open(output_path)
        layer_names = {layer.name for layer in result}
        assert layer_names == {"Background", "Guides", "1-image-template-circular", "2-image-template-circular"}

        img = result.composite(ignore_preview=True)
        assert img.getpixel((60, 160))[:3] == (230, 200, 0)  # slot 1 -> yellow
        assert img.getpixel((240, 160))[:3] == (150, 0, 200)  # slot 2 -> purple


class TestOverCapErrorFlow:
    def test_exceeding_cap_does_not_write_a_file(self, template_layouts, tmp_path):
        layout = get_layout(template_layouts, "rectangular")  # 2-slot fixture layout
        images = [
            flatten_source_psd(FIXTURES_DIR / "source_red.psd"),
            flatten_source_psd(FIXTURES_DIR / "source_blue.psd"),
            flatten_source_psd(FIXTURES_DIR / "source_green.psd"),
        ]
        output_path = tmp_path / "should_not_exist.psd"

        with pytest.raises(SlotCapExceededError):
            export_editable_psd(layout, images, output_path)

        assert not output_path.exists()
