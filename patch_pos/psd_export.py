"""Editable PSD export: the same composited sheet as
compositor.composite_sheet, written as a multi-layer .psd instead of a
flattened raster -- one movable/resizable layer per filled slot, plus a
Guides layer and a Background layer -- so an operator can manually nudge,
resize, or retouch a specific order's patches in Photoshop before
printing. This is an alternate, manual-editing path alongside (not a
replacement for) the automated PDF export in pdf_export.py.
"""

import math
import struct
from pathlib import Path

import numpy as np
import pytoshop.util
from PIL import Image, ImageDraw
from pytoshop import image_resources
from pytoshop.enums import ColorMode, Compression
from pytoshop.user import nested_layers

from .compositor import STROKE_COLOR, STROKE_WIDTH_PX, _patch_box, _trim_and_fit, check_cap
from .slots import Slot, TemplateLayout

# pytoshop's RLE encoder hits a broken optional Cython extension in this
# environment (NameError: packbits, never built for this Python/arch) --
# raw/uncompressed is the only reliably working option here, at the cost
# of a larger file than a real Photoshop save would produce.
_COMPRESSION = Compression.raw


def _encode_unicode_string_without_bogus_terminator(s: str) -> bytes:
    """Replaces pytoshop.util.encode_unicode_string, which writes a length
    of len(s)+1 plus a trailing null character. psd-tools' own reader (and
    its own writer, which uses the exact character count with no added
    terminator) doesn't strip that extra null, so every layer name comes
    back as e.g. '1-image-template\\x00'. Patched at import time so every
    layer name this module writes round-trips clean."""
    encoded = s.encode("utf_16_be")
    return struct.pack(">L", len(encoded) // 2) + encoded


pytoshop.util.encode_unicode_string = _encode_unicode_string_without_bogus_terminator

# nested_layers_to_psd never writes a ResolutionInfo (0x03ED) image
# resource, so without this the file has no embedded DPI and Photoshop
# falls back to displaying 72 -- even though the layers themselves are
# composited at the master template's native 300 DPI pixel grid (see
# compositor.py). Built by hand since pytoshop's image_resources module
# has no ResolutionInfo class; layout per the Adobe PSD spec: hRes/vRes as
# 16.16 fixed-point pixels-per-inch, then a 2-byte display-unit pair.
_RESOLUTION_INFO_ID = 1005


def _resolution_info_block(dpi: int) -> image_resources.GenericImageResourceBlock:
    fixed = round(dpi * 65536)
    data = struct.pack(">IhhIhh", fixed, 1, 1, fixed, 1, 1)
    return image_resources.GenericImageResourceBlock(resource_id=_RESOLUTION_INFO_ID, data=data)


def _pil_to_layer(name: str, image: Image.Image, top: int, left: int) -> nested_layers.Image:
    image = image.convert("RGBA")
    arr = np.asarray(image)
    h, w = arr.shape[:2]
    channels = {0: arr[:, :, 0], 1: arr[:, :, 1], 2: arr[:, :, 2], -1: arr[:, :, 3]}
    return nested_layers.Image(name=name, top=top, left=left, bottom=top + h, right=left + w, channels=channels)


def _guides_layer(layout: TemplateLayout, filled_slots: tuple[Slot, ...]) -> nested_layers.Image:
    """A single reference layer with the registration stroke for every
    filled slot -- cropped to just the region the strokes occupy (plus the
    stroke's own width) rather than the full canvas, to keep the file
    size proportional to how many slots are actually used."""
    boxes = [_patch_box(slot, layout.shape) for slot in filled_slots]
    pad = STROKE_WIDTH_PX
    canvas_w, canvas_h = layout.canvas_size
    left = max(0, math.floor(min(x for x, y, w, h in boxes)) - pad)
    top = max(0, math.floor(min(y for x, y, w, h in boxes)) - pad)
    right = min(canvas_w, math.ceil(max(x + w for x, y, w, h in boxes)) + pad)
    bottom = min(canvas_h, math.ceil(max(y + h for x, y, w, h in boxes)) + pad)

    guide = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
    draw = ImageDraw.Draw(guide)
    draw_shape = draw.ellipse if layout.shape == "circular" else draw.rectangle
    for x, y, w, h in boxes:
        draw_shape([x - left, y - top, x - left + w, y - top + h], outline=STROKE_COLOR, width=STROKE_WIDTH_PX)
    return _pil_to_layer("Guides", guide, top, left)


def export_editable_psd(
    layout: TemplateLayout,
    source_images: list[Image.Image],
    output_path: str | Path,
    dpi: int = 300,
) -> None:
    """Composite `source_images` into `layout`'s slots exactly like
    composite_sheet (same trim-and-fit, same patch box per slot), but
    write the result as a layered PSD: one named layer per filled slot
    ('1-image-template', ...), a 'Guides' layer with the cut/registration
    stroke, and a white 'Background' layer. Raises SlotCapExceededError /
    EmptySourceImageError under the same conditions as composite_sheet.
    """
    check_cap(len(source_images), layout)
    filled_slots = layout.slots[: len(source_images)]

    patch_layers = []
    for slot, image in zip(filled_slots, source_images):
        x, y, w, h = _patch_box(slot, layout.shape)
        fitted = _trim_and_fit(image, (round(w), round(h)), slot.name)
        patch_layers.append(_pil_to_layer(slot.name, fitted, round(y), round(x)))

    canvas_w, canvas_h = layout.canvas_size
    background = _pil_to_layer("Background", Image.new("RGB", (canvas_w, canvas_h), "white"), 0, 0)

    # nested_layers_to_psd wants layers listed topmost-first.
    layers = [_guides_layer(layout, filled_slots), *patch_layers, background] if filled_slots else [background]
    psd = nested_layers.nested_layers_to_psd(layers, ColorMode.rgb, compression=_COMPRESSION)
    psd.image_resources.blocks.append(_resolution_info_block(dpi))

    with open(output_path, "wb") as f:
        psd.write(f)
