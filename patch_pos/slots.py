"""Master template slot-layout extraction.

Coordinates for a Smart Object placeholder layer live in the layer's
``Trnf`` transform descriptor (SoLE/SoLd tagged block), not its outer
bbox, which reads as zero for these layers -- see PROJECT_INSTRUCTIONS.md
Appendix A. Plain pixel layers (used by test fixtures, since psd-tools
cannot author real Smart Object layers) don't carry that block, so
extraction falls back to the layer's bbox in that case.
"""

from dataclasses import dataclass

from psd_tools.constants import Tag

from .errors import UnknownShapeError

_GROUP_NAMES = {"rectangular": "RECTANGLES", "circular": "ROUNDS"}


@dataclass(frozen=True)
class Slot:
    name: str
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class TemplateLayout:
    shape: str
    canvas_size: tuple[int, int]
    slots: tuple[Slot, ...]

    @property
    def cap(self) -> int:
        return len(self.slots)


def extract_transform(layer) -> tuple[float, float, float, float]:
    """Return (x, y, w, h) for a template placeholder layer."""
    block = layer.tagged_blocks.get(Tag.SMART_OBJECT_LAYER_DATA2)
    if block is None:
        block = layer.tagged_blocks.get(Tag.SMART_OBJECT_LAYER_DATA1)
    if block is not None:
        trnf = [float(v) for v in block.data.data[b"Trnf"]]
        xs, ys = trnf[0::2], trnf[1::2]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)

    left, top, right, bottom = layer.bbox
    return float(left), float(top), float(right - left), float(bottom - top)


def _slot_sort_key(layer_name: str) -> int:
    """'3-image-template' / '3-image-template-circular' -> 3"""
    return int(layer_name.split("-", 1)[0])


def load_template_layouts(psd) -> dict[str, TemplateLayout]:
    """Read both the rectangular and circular slot layouts out of a master
    template PSD. Returns only the shapes whose group is actually present.
    """
    layouts: dict[str, TemplateLayout] = {}
    for shape, group_name in _GROUP_NAMES.items():
        matches = [layer for layer in psd if layer.name == group_name]
        if not matches:
            continue
        ordered_layers = sorted(matches[0], key=lambda layer: _slot_sort_key(layer.name))
        slots = tuple(
            Slot(layer.name, *extract_transform(layer)) for layer in ordered_layers
        )
        layouts[shape] = TemplateLayout(shape, tuple(psd.size), slots)
    return layouts


def get_layout(layouts: dict[str, TemplateLayout], shape: str) -> TemplateLayout:
    try:
        return layouts[shape]
    except KeyError:
        raise UnknownShapeError(shape, sorted(layouts)) from None
