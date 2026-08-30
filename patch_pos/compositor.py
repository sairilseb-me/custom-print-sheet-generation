"""Core compositing engine: flatten source PSDs onto a master template's
A4 canvas at each slot's exact position, in order.
"""

from pathlib import Path

from PIL import Image
from psd_tools import PSDImage

from .errors import SlotCapExceededError, SourceSizeMismatchError
from .slots import TemplateLayout


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


def composite_sheet(layout: TemplateLayout, source_images: list[Image.Image]) -> Image.Image:
    """Paste each source image into its slot, in order. Raises
    SlotCapExceededError if there are more images than slots, and
    SourceSizeMismatchError if an image isn't exactly its slot's size --
    source PSDs are expected to already be sized to match (see
    PROJECT_INSTRUCTIONS.md section 4); the engine does not resize/crop.
    """
    check_cap(len(source_images), layout)

    canvas = Image.new("RGB", layout.canvas_size, "white")
    for slot, image in zip(layout.slots, source_images):
        expected = (round(slot.w), round(slot.h))
        if image.size != expected:
            raise SourceSizeMismatchError(slot.name, expected, image.size)

        position = (round(slot.x), round(slot.y))
        if image.mode == "RGBA":
            canvas.paste(image, position, image)
        else:
            canvas.paste(image.convert("RGB"), position)
    return canvas
