"""Unit tests for the compositing math -- pure PIL operations, no PSD
parsing involved, per PROJECT_INSTRUCTIONS.md section 9.1.
"""

import pytest
from PIL import Image

from patch_pos.compositor import check_cap, composite_sheet, slot_label
from patch_pos.errors import EmptySourceImageError, SlotCapExceededError
from patch_pos.slots import Slot, TemplateLayout

RECT_LAYOUT = TemplateLayout(
    "rectangular",
    (400, 300),
    (
        Slot("1-image-template", 20, 20, 100, 60),
        Slot("2-image-template", 200, 20, 100, 60),
    ),
)

CIRCULAR_LAYOUT = TemplateLayout(
    "circular",
    (400, 300),
    (Slot("1-image-template-circular", 20, 20, 100, 100),),
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

    def test_off_size_source_is_stretched_to_fill_the_slot(self):
        # Real source PSDs vary in size/margin (see
        # PROJECT_INSTRUCTIONS.md section 4, "Decision -- trim and fit"),
        # so an off-size source is trimmed to content and stretched to
        # fill the slot exactly rather than rejected.
        wrong_size = Image.new("RGB", (50, 50), (255, 0, 0))

        sheet = composite_sheet(RECT_LAYOUT, [wrong_size])

        assert sheet.getpixel((70, 50)) == (255, 0, 0)  # fills the whole slot
        assert sheet.getpixel((250, 50)) == (255, 255, 255)  # slot 2 still empty

    def test_source_with_transparent_margin_is_trimmed_and_fit(self):
        # A source smaller than its slot, centered in a larger
        # transparent canvas -- exactly what real source PSDs with a
        # baked-in margin look like.
        source = Image.new("RGBA", (200, 120), (0, 0, 0, 0))
        content = Image.new("RGBA", (100, 60), (0, 255, 0, 255))
        source.paste(content, (50, 30))

        sheet = composite_sheet(RECT_LAYOUT, [source])

        # The trimmed green content now fills the entire slot -- no gap
        # between it and the slot boundary/stroke.
        assert sheet.getpixel((25, 25)) == (0, 255, 0)  # near slot's top-left corner
        assert sheet.getpixel((115, 75)) == (0, 255, 0)  # near slot's bottom-right corner

    def test_solid_black_background_is_not_treated_as_empty(self):
        # getbbox() on a plain RGB image treats pure black as "empty" --
        # a solid black-background patch (common in this library) must
        # not be wrongly flagged as blank.
        black = Image.new("RGB", (100, 60), (0, 0, 0))

        sheet = composite_sheet(RECT_LAYOUT, [black])  # must not raise

        assert sheet.getpixel((70, 50)) == (0, 0, 0)

    def test_fully_transparent_source_raises(self):
        blank = Image.new("RGBA", (100, 60), (0, 0, 0, 0))

        with pytest.raises(EmptySourceImageError) as exc_info:
            composite_sheet(RECT_LAYOUT, [blank])
        assert exc_info.value.slot_name == "1-image-template"


class TestSlotStroke:
    """5px black inside stroke drawn around each filled slot, as a
    cut/registration guide -- rectangle for rectangular slots, circle
    for circular slots. Only filled slots get one."""

    def test_rectangular_slot_gets_inside_stroke(self):
        # Slot 1: x=20,y=20,w=100,h=60 -> boundary x:20-120, y:20-80.
        red = Image.new("RGB", (100, 60), (255, 0, 0))

        sheet = composite_sheet(RECT_LAYOUT, [red])

        # Outer edge of the stroke sits exactly on the slot boundary.
        assert sheet.getpixel((20, 50)) == (0, 0, 0)
        # Stroke grows inward 5px, not outward -- nothing outside the slot.
        assert sheet.getpixel((19, 50)) == (255, 255, 255)
        # Interior (away from the 5px band) keeps the pasted image color.
        assert sheet.getpixel((70, 50)) == (255, 0, 0)

    def test_empty_slot_gets_no_stroke(self):
        red = Image.new("RGB", (100, 60), (255, 0, 0))

        sheet = composite_sheet(RECT_LAYOUT, [red])  # slot 2 left empty

        assert sheet.getpixel((200, 50)) == (255, 255, 255)  # no stroke drawn

    def test_circular_slot_gets_circular_inside_stroke(self):
        # Slot: x=20,y=20,w=100,h=100 -> a circle inscribed in that
        # square, horizontal edges at x=20 and x=120 along the vertical center.
        yellow = Image.new("RGB", (100, 100), (230, 200, 0))

        sheet = composite_sheet(CIRCULAR_LAYOUT, [yellow])

        assert sheet.getpixel((20, 70)) == (0, 0, 0)  # left edge of the circle
        assert sheet.getpixel((19, 70)) == (255, 255, 255)  # nothing outside it
        assert sheet.getpixel((70, 70)) == (230, 200, 0)  # interior untouched
        # A rectangle stroke would blacken the square's corner; a circle
        # stroke must not, since the corner lies outside the circle --
        # it stays whatever was pasted there (the square source image
        # fills its whole bounding box, corners included).
        assert sheet.getpixel((21, 21)) == (230, 200, 0)
