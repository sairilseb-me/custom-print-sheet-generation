"""Builds the small, checked-in fixture PSDs used by the integration
tests -- NOT the production master template or product library (see
PROJECT_INSTRUCTIONS.md section 9.2). Run this script to regenerate the
fixtures if they're ever deleted:

    python tests/fixtures/generate_fixtures.py

psd-tools can only author plain pixel layers, not real Smart Object
layers, so the fixture master template's slots are extracted via bbox
rather than the Trnf transform descriptor the real production template
uses. The Trnf extraction path is covered separately by unit tests with
mocked psd-tools layer objects (tests/unit/test_slots.py), and by a
manual/CLI run against the real template (see PROJECT_INSTRUCTIONS.md
section 8, step 2) -- both code paths share the same `extract_transform`
function.
"""

from pathlib import Path

from PIL import Image
from psd_tools import PSDImage

FIXTURES_DIR = Path(__file__).parent

# Small stand-in layout: 2 rectangular slots (100x60) + 2 circular slots
# (80x80) on a 400x300 canvas -- same two-group structure as the real
# template (RECTANGLES / ROUNDS groups, numbered "N-image-template" /
# "N-image-template-circular" layers), just much smaller.
CANVAS_SIZE = (400, 300)
RECT_SLOTS = [
    ("1-image-template", 20, 20, 100, 60),
    ("2-image-template", 200, 20, 100, 60),
]
CIRCULAR_SLOTS = [
    ("1-image-template-circular", 20, 120, 80, 80),
    ("2-image-template-circular", 200, 120, 80, 80),
]


def _add_layer(psd: PSDImage, group, name: str, left: int, top: int, w: int, h: int, color):
    image = Image.new("RGB", (w, h), color)
    layer = psd.create_pixel_layer(image, name=name, top=top, left=left)
    layer.move_to_group(group)


def build_mini_template() -> None:
    psd = PSDImage.new(mode="RGB", size=CANVAS_SIZE, color=(255, 255, 255))

    rect_group = psd.create_group(name="RECTANGLES")
    for name, left, top, w, h in RECT_SLOTS:
        _add_layer(psd, rect_group, name, left, top, w, h, (200, 200, 200))

    round_group = psd.create_group(name="ROUNDS")
    for name, left, top, w, h in CIRCULAR_SLOTS:
        _add_layer(psd, round_group, name, left, top, w, h, (200, 200, 200))

    psd.save(FIXTURES_DIR / "mini_template.psd")


def build_source(filename: str, size: tuple[int, int], color: tuple[int, int, int]) -> None:
    psd = PSDImage.new(mode="RGB", size=size, color=(255, 255, 255))
    image = Image.new("RGB", size, color)
    psd.create_pixel_layer(image, name="art", top=0, left=0)
    psd.save(FIXTURES_DIR / filename)


def main() -> None:
    build_mini_template()
    # Sized to exactly match the rectangular fixture slots (100x60).
    build_source("source_red.psd", (100, 60), (255, 0, 0))
    build_source("source_blue.psd", (100, 60), (0, 0, 255))
    build_source("source_green.psd", (100, 60), (0, 200, 0))
    # Sized to exactly match the circular fixture slots (80x80).
    build_source("source_yellow_circular.psd", (80, 80), (230, 200, 0))
    build_source("source_purple_circular.psd", (80, 80), (150, 0, 200))
    # Deliberately wrong size, for the mismatch-error test.
    build_source("source_wrong_size.psd", (50, 50), (0, 0, 0))
    print(f"Wrote fixtures to {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
