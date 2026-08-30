"""In-memory Current Order (cart) state -- see PROJECT_INSTRUCTIONS.md
section 5. Template shape is chosen once per order and locked while it
has items, since products are shape-specific (section 4); quantity
drives slot count (section 5, "Decision -- quantity drives slot count").
"""

from dataclasses import dataclass

from .library import ProductRecord


class OrderError(Exception):
    pass


class TemplateNotSetError(OrderError):
    def __init__(self) -> None:
        super().__init__("Order has no template selected yet -- call set_template() first")


class ShapeMismatchError(OrderError):
    def __init__(self, product_shape: str, order_shape: str):
        self.product_shape = product_shape
        self.order_shape = order_shape
        super().__init__(
            f"Product is {product_shape!r} but this order's template is {order_shape!r}"
        )


class TemplateLockedError(OrderError):
    def __init__(self) -> None:
        super().__init__("Can't change template while the order has items -- clear it first")


class NoSuchLineError(OrderError):
    def __init__(self, folder_path: str):
        self.folder_path = folder_path
        super().__init__(f"No such line in order: {folder_path}")


@dataclass
class OrderLine:
    product: ProductRecord
    quantity: int


class Order:
    def __init__(self) -> None:
        self.template_shape: str | None = None
        self._lines: dict[str, OrderLine] = {}

    @property
    def lines(self) -> list[OrderLine]:
        return list(self._lines.values())

    def set_template(self, shape: str) -> None:
        if self._lines:
            raise TemplateLockedError()
        self.template_shape = shape

    def add(self, product: ProductRecord, quantity: int = 1) -> None:
        if self.template_shape is None:
            raise TemplateNotSetError()
        if product.shape != self.template_shape:
            raise ShapeMismatchError(product.shape, self.template_shape)

        key = str(product.folder_path)
        existing = self._lines.get(key)
        if existing is not None:
            existing.quantity += quantity
        else:
            self._lines[key] = OrderLine(product=product, quantity=quantity)

    def set_quantity(self, folder_path: str, quantity: int) -> None:
        if quantity <= 0:
            self._lines.pop(folder_path, None)
            return
        line = self._lines.get(folder_path)
        if line is None:
            raise NoSuchLineError(folder_path)
        line.quantity = quantity

    def remove(self, folder_path: str) -> None:
        self._lines.pop(folder_path, None)

    def clear(self) -> None:
        self._lines.clear()
        self.template_shape = None

    def total_items(self) -> int:
        return sum(line.quantity for line in self._lines.values())

    def expand_to_slot_order(self) -> list[ProductRecord]:
        """One ProductRecord per slot to fill, in order -- a line with
        quantity N contributes N consecutive slots."""
        expanded: list[ProductRecord] = []
        for line in self._lines.values():
            expanded.extend([line.product] * line.quantity)
        return expanded
