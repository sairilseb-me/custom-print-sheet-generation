"""Unit tests for the compositing math -- pure PIL operations, no PSD
parsing involved, per PROJECT_INSTRUCTIONS.md section 9.1.
"""

import pytest
from PIL import Image

from patch_pos.compositor import check_cap, composite_sheet, slot_label
from patch_pos.errors import SlotCapExceededError, SourceSizeMismatchError
from patch_pos.slots import Slot, TemplateLayout

RECT_LAYOUT = TemplateLayout(
    "rectangular",
    (400, 300),
    (
        Slot("1-image-template", 20, 20, 100, 60),
        Slot("2-image-template", 200, 20, 100, 60),
    ),
)


class TestSlotLabel:
    def test_rectangular(self):
        assert slot_label(1, "rectangular") == "1-image-template"
        assert slot_label(8, "rectangular") == "8-image-template"

    def test_circular(self):
        assert slot_label(1, "circular") == "1-image-template-circular"
        assert slot_label(6, "circular") == "6-image-template-circular"


class TestCheckCap:
    def test_empty_selection_ok(self):
        check_cap(0, RECT_LAYOUT)  # must not raise

    def test_exactly_at_cap_ok(self):
        check_cap(2, RECT_LAYOUT)  # must not raise

    def test_one_over_cap_raises(self):
        with pytest.raises(SlotCapExceededError) as exc_info:
            check_cap(3, RECT_LAYOUT)
        assert exc_info.value.requested == 3
        assert exc_info.value.cap == 2
        assert exc_info.value.shape == "rectangular"


class TestCompositeSheet:
    def test_places_images_at_slot_positions(self):
        red = Image.new("RGB", (100, 60), (255, 0, 0))
        blue = Image.new("RGB", (100, 60), (0, 0, 255))

        sheet = composite_sheet(RECT_LAYOUT, [red, blue])

        assert sheet.size == (400, 300)
        assert sheet.getpixel((70, 50)) == (255, 0, 0)  # inside slot 1
        assert sheet.getpixel((250, 50)) == (0, 0, 255)  # inside slot 2
        assert sheet.getpixel((5, 5)) == (255, 255, 255)  # outside any slot

    def test_partial_order_leaves_remaining_slots_blank(self):
        red = Image.new("RGB", (100, 60), (255, 0, 0))

        sheet = composite_sheet(RECT_LAYOUT, [red])

        assert sheet.getpixel((70, 50)) == (255, 0, 0)
        assert sheet.getpixel((250, 50)) == (255, 255, 255)  # slot 2 empty

    def test_over_cap_raises_before_compositing(self):
        red = Image.new("RGB", (100, 60), (255, 0, 0))
        with pytest.raises(SlotCapExceededError):
            composite_sheet(RECT_LAYOUT, [red, red, red])

    def test_size_mismatch_raises(self):
        wrong_size = Image.new("RGB", (50, 50), (0, 0, 0))
        with pytest.raises(SourceSizeMismatchError) as exc_info:
            composite_sheet(RECT_LAYOUT, [wrong_size])
        assert exc_info.value.slot_name == "1-image-template"
        assert exc_info.value.expected == (100, 60)
        assert exc_info.value.actual == (50, 50)

    def test_does_not_auto_resize_or_crop(self):
        # A mismatch must be a hard error, never a silent resize -- see
        # PROJECT_INSTRUCTIONS.md section 4 ("Decision -- source size
        # mismatch").
        wrong_size = Image.new("RGB", (50, 50), (0, 0, 0))
        with pytest.raises(SourceSizeMismatchError):
            composite_sheet(RECT_LAYOUT, [wrong_size])
