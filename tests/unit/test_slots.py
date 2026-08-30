"""Unit tests for slot-coordinate extraction.

The Trnf-based path (used by the real production master template, where
placeholders are Smart Object layers) is tested here with mocked
psd-tools layer objects, per PROJECT_INSTRUCTIONS.md section 9.1
("Mock the filesystem and PSD library calls in unit tests"). It's also
exercised for real against the actual template PSD via the CLI -- see
PROJECT_INSTRUCTIONS.md section 8, step 2.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from psd_tools.constants import Tag

from patch_pos.errors import UnknownShapeError
from patch_pos.slots import (
    Slot,
    TemplateLayout,
    _slot_sort_key,
    extract_transform,
    get_layout,
    load_template_layouts,
)


def _mock_smart_object_layer(trnf_values):
    """A mock layer whose tagged_blocks exposes a Trnf transform
    descriptor, like a real Smart Object placeholder layer."""
    block = SimpleNamespace(data=SimpleNamespace(data={b"Trnf": trnf_values}))
    tagged_blocks = MagicMock()
    tagged_blocks.get.side_effect = lambda tag: block if tag == Tag.SMART_OBJECT_LAYER_DATA2 else None
    return SimpleNamespace(tagged_blocks=tagged_blocks)


def _mock_plain_pixel_layer(bbox):
    tagged_blocks = MagicMock()
    tagged_blocks.get.return_value = None
    return SimpleNamespace(tagged_blocks=tagged_blocks, bbox=bbox)


class TestExtractTransform:
    def test_smart_object_trnf_axis_aligned(self):
        # Trnf is 4 (x, y) corner pairs: top-left, top-right, bottom-right, bottom-left.
        trnf = [164.0, 167.0, 1139.0, 167.0, 1139.0, 842.0, 164.0, 842.0]
        layer = _mock_smart_object_layer(trnf)
        assert extract_transform(layer) == (164.0, 167.0, 975.0, 675.0)

    def test_smart_object_falls_back_to_data1_block(self):
        trnf = [0.0, 0.0, 10.0, 0.0, 10.0, 10.0, 0.0, 10.0]
        block = SimpleNamespace(data=SimpleNamespace(data={b"Trnf": trnf}))
        tagged_blocks = MagicMock()

        def get(tag):
            return block if tag == Tag.SMART_OBJECT_LAYER_DATA1 else None

        tagged_blocks.get.side_effect = get
        layer = SimpleNamespace(tagged_blocks=tagged_blocks)
        assert extract_transform(layer) == (0.0, 0.0, 10.0, 10.0)

    def test_plain_pixel_layer_uses_bbox(self):
        layer = _mock_plain_pixel_layer((20, 20, 120, 80))
        assert extract_transform(layer) == (20.0, 20.0, 100.0, 60.0)

    def test_outer_bbox_ignored_when_trnf_present(self):
        # Real Smart Object layers report a zero/irrelevant outer bbox --
        # extraction must prefer Trnf and never touch .bbox in that case.
        trnf = [164.0, 167.0, 1139.0, 167.0, 1139.0, 842.0, 164.0, 842.0]
        layer = _mock_smart_object_layer(trnf)
        layer.bbox = (0, 0, 0, 0)
        assert extract_transform(layer) == (164.0, 167.0, 975.0, 675.0)


class TestSlotSortKey:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("1-image-template", 1),
            ("8-image-template", 8),
            ("3-image-template-circular", 3),
            ("10-image-template", 10),
        ],
    )
    def test_extracts_leading_index(self, name, expected):
        assert _slot_sort_key(name) == expected


class TestGetLayout:
    def test_returns_matching_layout(self):
        layout = TemplateLayout("rectangular", (400, 300), (Slot("1-image-template", 0, 0, 10, 10),))
        layouts = {"rectangular": layout}
        assert get_layout(layouts, "rectangular") is layout

    def test_raises_for_missing_shape(self):
        layouts = {"rectangular": TemplateLayout("rectangular", (400, 300), ())}
        with pytest.raises(UnknownShapeError) as exc_info:
            get_layout(layouts, "circular")
        assert exc_info.value.shape == "circular"
        assert exc_info.value.available == ["rectangular"]


class _FakeGroup(list):
    """A list that also carries a `.name`, like a psd-tools Group -- plain
    SimpleNamespace can't be iterated over with `for x in obj` since that
    looks up `__iter__` on the type, not the instance."""

    def __init__(self, name, layers):
        super().__init__(layers)
        self.name = name


class TestLoadTemplateLayouts:
    def test_only_present_groups_are_returned(self):
        rect_layer = _mock_plain_pixel_layer((20, 20, 120, 80))
        rect_layer.name = "1-image-template"
        rect_group = _FakeGroup("RECTANGLES", [rect_layer])

        psd = _FakeGroup("psd", [rect_group])
        psd.size = (400, 300)

        layouts = load_template_layouts(psd)

        assert set(layouts) == {"rectangular"}
        assert layouts["rectangular"].cap == 1
        assert layouts["rectangular"].slots[0].name == "1-image-template"
