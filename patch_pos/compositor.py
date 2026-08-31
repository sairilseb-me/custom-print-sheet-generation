"""Core compositing engine: flatten source PSDs onto a master template's
A4 canvas at each slot's exact position, in order.
"""

from pathlib import Path

from PIL import Image, ImageDraw
from psd_tools import PSDImage

from .errors import EmptySourceImageError, SlotCapExceededError
from .slots import TemplateLayout

STROKE_WIDTH_PX = 5
STROKE_COLOR = "black"

# Confirmed against the operator's real-world size guides (rendered A4
# reference PDFs whose boxes/circles sit at the exact same grid positions
# as the RECTANGLES/ROUNDS slots -- centers matched slot centers to
# sub-pixel precision). Master templates are authored at 300 DPI (see
# PROJECT_INSTRUCTIONS.md section 3). Measured finished sizes, stable
# across every pixel-detection threshold tried (not measurement noise):
#   rectangular: 930x628 inside a 975x675 slot -> 22.5px margin on the
#     left/right sides, 23.5px margin on the top/bottom sides (the two
#     axes are NOT the same margin -- confirmed by direct measurement).
#   circular: 933px diameter inside a 975x975 slot -> 21px margin all
#     the way around (uniform, since a circle has only one measurement).
RECT_PATCH_MARGIN_X_PX = 22.5
RECT_PATCH_MARGIN_Y_PX = 23.5
CIRCULAR_PATCH_MARGIN_PX = 21.0


def slot_label(index: int, shape: str) -> str:
    """1-based slot index -> the layer-name convention used throughout the
    library ('3-image-template', '3-image-template-circular', ...)."""
    suffix = "-circular" if shape == "circular" else ""
    return f"{index}-image-template{suffix}"


def check_cap(item_count: int, layout: TemplateLayout) -> None:
    if item_count > layout.cap:
        raise SlotCapExceededError(item_count, layout.cap, layout.shape)


def flatten_source_psd(path: str | Path) -> Image.Image:
    """Open a product's source PSD and return its flattened raster image."""
    return PSDImage.open(path).composite()


def _trim_and_fit(image: Image.Image, target_size: tuple[int, int], slot_name: str) -> Image.Image:
    """Crop away any transparent margin around the actual artwork, then
    stretch to exactly fill the slot. Real source PSDs vary in how much
    margin they carry (some are full-bleed, some have a baked-in margin
    of a different size per file) -- trimming to content and fitting to
    the slot is what eliminates a visible gap between the patch and its
    slot boundary/stroke, regardless of how a given file was authored.
    """
    # getbbox() on a plain RGB image treats pure black as "empty" (no
    # alpha channel to distinguish opaque black from nothing) -- convert
    # to RGBA first so a solid black-background patch isn't wrongly
    # flagged as blank.
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    bbox = image.getbbox()
    if bbox is None:
        raise EmptySourceImageError(slot_name)
    return image.crop(bbox).resize(target_size)


def _patch_box(slot, shape: str) -> tuple[float, float, float, float]:
    """Return (x, y, w, h) of the box the artwork and stroke should
    occupy -- inset from the raw slot by the confirmed real-world patch
    margin for the shape, centered in the slot."""
    if shape == "circular":
        m = CIRCULAR_PATCH_MARGIN_PX
        return slot.x + m, slot.y + m, slot.w - 2 * m, slot.h - 2 * m
    mx, my = RECT_PATCH_MARGIN_X_PX, RECT_PATCH_MARGIN_Y_PX
    return slot.x + mx, slot.y + my, slot.w - 2 * mx, slot.h - 2 * my


def composite_sheet(layout: TemplateLayout, source_images: list[Image.Image]) -> Image.Image:
    """Paste each source image into its slot, in order -- trimmed to its
    actual content and stretched to fill its patch box exactly (see
    _trim_and_fit and _patch_box) -- with a 5px inside stroke drawn around
    each filled slot's patch box (rectangle for the rectangular template,
    circle for the circular one) as a cut/registration guide. Only filled
    slots get a stroke -- empty/unused slots stay blank. Raises
    SlotCapExceededError if there are more images than slots, and
    EmptySourceImageError if a source is fully blank/transparent.
    """
    check_cap(len(source_images), layout)

    canvas = Image.new("RGB", layout.canvas_size, "white")
    draw = ImageDraw.Draw(canvas)
    for slot, image in zip(layout.slots, source_images):
        x, y, w, h = _patch_box(slot, layout.shape)
        target_size = (round(w), round(h))
        image = _trim_and_fit(image, target_size, slot.name)

        position = (round(x), round(y))
        if image.mode == "RGBA":
            canvas.paste(image, position, image)
        else:
            canvas.paste(image.convert("RGB"), position)

        # PIL draws stroke `width` growing inward from the given
        # boundary, so the patch box's own coordinates are already the
        # correct "inside stroke" path -- no further inset math needed.
        bbox = [x, y, x + w, y + h]
        draw_shape = draw.ellipse if layout.shape == "circular" else draw.rectangle
        draw_shape(bbox, outline=STROKE_COLOR, width=STROKE_WIDTH_PX)
    return canvas
