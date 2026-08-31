"""Error types for the print sheet compositing engine."""


class PatchPosError(Exception):
    """Base class for all patch_pos errors."""


class UnknownShapeError(PatchPosError):
    def __init__(self, shape: str, available: list[str]):
        self.shape = shape
        self.available = available
        super().__init__(
            f"Template has no {shape!r} layout (available: {available})"
        )


class SlotCapExceededError(PatchPosError):
    def __init__(self, requested: int, cap: int, shape: str):
        self.requested = requested
        self.cap = cap
        self.shape = shape
        super().__init__(
            f"Order has {requested} item(s) but the {shape!r} template only "
            f"has {cap} slot(s)"
        )


class EmptySourceImageError(PatchPosError):
    """A source PSD flattened to a fully blank/transparent image -- there's
    no content bounding box to trim to and fit into the slot."""

    def __init__(self, slot_name: str):
        self.slot_name = slot_name
        super().__init__(f"Source image for slot {slot_name!r} is fully blank/transparent")
