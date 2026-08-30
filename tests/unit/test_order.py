"""Unit tests for Current Order (cart) state -- pure Python, no I/O.
See PROJECT_INSTRUCTIONS.md section 9.2 ("Add-to-order / quantity
change / remove updates order state and totals correctly").
"""

from pathlib import Path

import pytest

from patch_pos.library import ProductRecord
from patch_pos.order import (
    NoSuchLineError,
    Order,
    ShapeMismatchError,
    TemplateLockedError,
    TemplateNotSetError,
)


def _product(sku: str, shape: str = "rectangular") -> ProductRecord:
    folder = Path(f"/fake/{sku}")
    return ProductRecord(
        sku=sku,
        sku_number=int(sku.split("-")[-1]),
        name=sku,
        folder_path=folder,
        shape=shape,
        source_psd_path=folder / "3x2-images" / "1-image-template.psd",
        thumbnail_path=None,
    )


class TestSetTemplate:
    def test_sets_template_on_empty_order(self):
        order = Order()
        order.set_template("rectangular")
        assert order.template_shape == "rectangular"

    def test_raises_if_order_has_items(self):
        order = Order()
        order.set_template("rectangular")
        order.add(_product("MP-P-1"))

        with pytest.raises(TemplateLockedError):
            order.set_template("circular")


class TestAdd:
    def test_raises_if_no_template_selected(self):
        order = Order()
        with pytest.raises(TemplateNotSetError):
            order.add(_product("MP-P-1"))

    def test_raises_on_shape_mismatch(self):
        order = Order()
        order.set_template("rectangular")
        with pytest.raises(ShapeMismatchError):
            order.add(_product("MP-P-1", shape="circular"))

    def test_adds_new_line_with_default_quantity_one(self):
        order = Order()
        order.set_template("rectangular")
        order.add(_product("MP-P-1"))

        assert order.total_items() == 1
        assert len(order.lines) == 1

    def test_adding_same_product_again_increments_quantity(self):
        order = Order()
        order.set_template("rectangular")
        product = _product("MP-P-1")
        order.add(product)
        order.add(product, quantity=2)

        assert order.total_items() == 3
        assert len(order.lines) == 1  # still one line, not two

    def test_empty_selection_has_zero_total(self):
        order = Order()
        assert order.total_items() == 0


class TestSetQuantity:
    def test_updates_existing_line(self):
        order = Order()
        order.set_template("rectangular")
        product = _product("MP-P-1")
        order.add(product)

        order.set_quantity(str(product.folder_path), 5)

        assert order.total_items() == 5

    def test_zero_quantity_removes_the_line(self):
        order = Order()
        order.set_template("rectangular")
        product = _product("MP-P-1")
        order.add(product)

        order.set_quantity(str(product.folder_path), 0)

        assert order.lines == []

    def test_raises_for_unknown_line(self):
        order = Order()
        order.set_template("rectangular")
        with pytest.raises(NoSuchLineError):
            order.set_quantity("/nonexistent", 3)


class TestRemove:
    def test_removes_line_and_leaves_others(self):
        order = Order()
        order.set_template("rectangular")
        a, b = _product("MP-P-1"), _product("MP-P-2")
        order.add(a)
        order.add(b)

        order.remove(str(a.folder_path))

        assert [line.product.sku for line in order.lines] == ["MP-P-2"]

    def test_removing_unknown_line_is_a_no_op(self):
        order = Order()
        order.set_template("rectangular")
        order.remove("/nonexistent")  # must not raise


class TestClear:
    def test_clears_lines_and_unlocks_template(self):
        order = Order()
        order.set_template("rectangular")
        order.add(_product("MP-P-1"))

        order.clear()

        assert order.lines == []
        assert order.template_shape is None
        order.set_template("circular")  # must not raise -- unlocked


class TestExpandToSlotOrder:
    def test_quantity_expands_to_repeated_consecutive_slots(self):
        order = Order()
        order.set_template("rectangular")
        a, b = _product("MP-P-1"), _product("MP-P-2")
        order.add(a, quantity=2)
        order.add(b, quantity=1)

        expanded = order.expand_to_slot_order()

        assert [p.sku for p in expanded] == ["MP-P-1", "MP-P-1", "MP-P-2"]
