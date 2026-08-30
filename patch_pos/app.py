"""pywebview shell: a native desktop window rendering the HTML/CSS/JS
frontend, with an `Api` bridge exposed to the frontend as
`pywebview.api.*` for everything the UI needs -- library scan/search,
the Current Order cart, print sheet generation, and native dialogs.

`Api` doesn't reach for the global `webview.windows[0]` -- its window is
injected via the `.window` attribute after creation, so dialog logic can
be unit tested against a fake window object without a real GUI (see
PROJECT_INSTRUCTIONS.md section 9.3 on mocking the js_api bridge).

Every state-changing/reading method except the two dialog helpers is
wrapped by `_api_method`, which never lets an exception cross the JS
bridge -- it's logged (section 6, "Decision -- error/crash surfacing")
and turned into `{"ok": False, "error": "..."}` for the frontend to show
as a plain-language banner.
"""

import base64
import functools
import sys
from pathlib import Path

import webview
from psd_tools import PSDImage

from . import catalog, compositor, library, pdf_export, slots, thumbnails
from .logging_setup import configure_logging, data_dir_for_library, get_logger
from .order import Order

if getattr(sys, "frozen", False):
    # Inside a PyInstaller bundle, bundled data files (see build.spec)
    # extract to sys._MEIPASS instead of living next to this source file.
    FRONTEND_DIR = Path(sys._MEIPASS) / "frontend"
else:
    FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
DEFAULT_WINDOW_SIZE = (1200, 800)
MIN_WINDOW_SIZE = (900, 600)


def default_master_template_path(library_root: Path) -> Path:
    """Derived from the real flash-drive layout confirmed in
    PROJECT_INSTRUCTIONS.md section 3 -- the master template lives in a
    'MP Templates/PATCH/' folder that's a sibling of the scanned library
    root. Revisit once the (v1-deferred) Templates panel lets this be
    configured directly instead of derived."""
    return library_root.parent / "MP Templates" / "PATCH" / "A4-PATCH-TEMPLATE-NO MIRROR.psd"


def _serialize_product(product: library.ProductRecord) -> dict:
    return {
        "folder_path": str(product.folder_path),
        "sku": product.sku,
        "name": product.name,
        "shape": product.shape,
    }


def _api_method(fn):
    """Never let an exception cross the JS bridge -- log it and return a
    structured error the frontend can show as a banner."""

    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        try:
            result = fn(self, *args, **kwargs)
        except Exception as exc:
            get_logger().exception("Api.%s failed", fn.__name__)
            return {"ok": False, "error": str(exc)}
        result = dict(result or {})
        result.setdefault("ok", True)
        return result

    return wrapper


class Api:
    def __init__(self) -> None:
        self.window: webview.Window | None = None
        self.order = Order()
        self.library_root: Path | None = None
        self.data_dir: Path | None = None
        self.catalog_conn = None
        self.template_layouts: dict[str, slots.TemplateLayout] | None = None

    # -- native dialogs --------------------------------------------------

    def select_library_folder(self) -> str | None:
        """Native folder picker -- used for 'Rescan Library' and picking
        an external library path, per PROJECT_INSTRUCTIONS.md section 4.
        """
        results = self.window.create_file_dialog(webview.FileDialog.FOLDER)
        return results[0] if results else None

    def select_pdf_save_path(self, default_filename: str = "print_sheet.pdf") -> str | None:
        """Native save dialog with no pre-filled default path -- every
        'Generate Print Sheet' click prompts fresh, per
        PROJECT_INSTRUCTIONS.md section 5, point 7 ("blank save dialog
        every time")."""
        results = self.window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=default_filename,
            file_types=("PDF Files (*.pdf)",),
        )
        return results[0] if results else None

    # -- library / catalog -------------------------------------------------

    def _require(self, condition: bool, message: str) -> None:
        if not condition:
            raise RuntimeError(message)

    def _require_catalog(self) -> None:
        self._require(self.catalog_conn is not None, "No library scanned yet -- run Rescan Library first")

    @_api_method
    def rescan_library(self, root_path: str | None = None) -> dict:
        if root_path is None:
            self._require(self.library_root is not None, "No library folder selected yet")
            root = self.library_root
        else:
            root = Path(root_path)

        self.library_root = root
        self.data_dir = data_dir_for_library(root)
        configure_logging(self.data_dir)

        scan_result = library.scan_library(root)
        self.catalog_conn = catalog.open_catalog(self.data_dir / "catalog.db")
        catalog.save_scan(self.catalog_conn, scan_result)

        template_psd = PSDImage.open(default_master_template_path(root))
        self.template_layouts = slots.load_template_layouts(template_psd)

        info = catalog.get_library_info(self.catalog_conn)
        return {
            "total_products": info.total_products,
            "total_size_bytes": info.total_size_bytes,
            "last_scan_at": info.last_scan_at,
            "template_shapes": sorted(self.template_layouts),
        }

    @_api_method
    def search_products(
        self,
        query: str = "",
        shape: str | None = None,
        sort: str = "sku",
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """The frontend passes shape=<order's current template> once one
        is picked, so the grid only shows products that could actually
        be added (a mismatched product would otherwise just error on
        add) -- see PROJECT_INSTRUCTIONS.md section 5, point 3."""
        self._require_catalog()
        products, total = catalog.search_products(
            self.catalog_conn, query=query, shape=shape, sort=sort, limit=limit, offset=offset
        )
        return {"products": [_serialize_product(p) for p in products], "total": total}

    @_api_method
    def get_thumbnail(self, folder_path: str) -> dict:
        self._require_catalog()
        product = catalog.get_product_by_folder(self.catalog_conn, folder_path)
        self._require(product is not None, f"Unknown product: {folder_path}")

        data = thumbnails.get_thumbnail_bytes(product, cache_dir=self.data_dir / "thumbnail_cache")
        mime = "image/jpeg" if product.thumbnail_path else "image/png"
        return {"data_url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"}

    @_api_method
    def get_library_info(self) -> dict:
        self._require_catalog()
        info = catalog.get_library_info(self.catalog_conn)
        return {
            "total_products": info.total_products,
            "total_size_bytes": info.total_size_bytes,
            "last_scan_at": info.last_scan_at,
        }

    @_api_method
    def get_disk_usage(self) -> dict:
        self._require(self.library_root is not None, "No library selected yet")
        usage = library.get_disk_usage(self.library_root)
        return {"total_bytes": usage.total_bytes, "used_bytes": usage.used_bytes, "free_bytes": usage.free_bytes}

    # -- current order -----------------------------------------------------

    def _order_summary(self) -> dict:
        cap = None
        if self.order.template_shape and self.template_layouts:
            layout = self.template_layouts.get(self.order.template_shape)
            cap = layout.cap if layout else None
        total = self.order.total_items()
        return {
            "template_shape": self.order.template_shape,
            "lines": [
                {
                    "folder_path": str(line.product.folder_path),
                    "sku": line.product.sku,
                    "name": line.product.name,
                    "quantity": line.quantity,
                }
                for line in self.order.lines
            ],
            "total_items": total,
            "cap": cap,
            "over_cap": cap is not None and total > cap,
        }

    @_api_method
    def set_order_template(self, shape: str) -> dict:
        self.order.set_template(shape)
        return self._order_summary()

    @_api_method
    def add_to_order(self, folder_path: str, quantity: int = 1) -> dict:
        self._require_catalog()
        product = catalog.get_product_by_folder(self.catalog_conn, folder_path)
        self._require(product is not None, f"Unknown product: {folder_path}")
        self.order.add(product, quantity=quantity)
        return self._order_summary()

    @_api_method
    def set_order_quantity(self, folder_path: str, quantity: int) -> dict:
        self.order.set_quantity(folder_path, quantity)
        return self._order_summary()

    @_api_method
    def remove_from_order(self, folder_path: str) -> dict:
        self.order.remove(folder_path)
        return self._order_summary()

    @_api_method
    def clear_order(self) -> dict:
        self.order.clear()
        return self._order_summary()

    @_api_method
    def get_order(self) -> dict:
        return self._order_summary()

    # -- print sheet generation --------------------------------------------

    @_api_method
    def generate_print_sheet(self) -> dict:
        self._require(self.order.template_shape is not None, "Pick a template before generating")
        self._require(self.template_layouts is not None, "No library/template loaded yet")
        layout = slots.get_layout(self.template_layouts, self.order.template_shape)

        ordered_products = self.order.expand_to_slot_order()
        self._require(len(ordered_products) > 0, "Order is empty")
        compositor.check_cap(len(ordered_products), layout)

        save_path = self.select_pdf_save_path(default_filename="print_sheet.pdf")
        if save_path is None:
            return {"cancelled": True}

        images = [compositor.flatten_source_psd(p.source_psd_path) for p in ordered_products]
        sheet = compositor.composite_sheet(layout, images)
        pdf_export.export_pdf(sheet, save_path)

        get_logger().info(
            "Generated print sheet: %s (%d/%d slots)", save_path, len(ordered_products), layout.cap
        )
        self.order.clear()

        return {"path": save_path, "slots_used": len(ordered_products), "cap": layout.cap}


def create_app_window(api: Api | None = None) -> webview.Window:
    api = api or Api()
    window = webview.create_window(
        "Print Sheet POS",
        url=str(FRONTEND_DIR / "index.html"),
        js_api=api,
        width=DEFAULT_WINDOW_SIZE[0],
        height=DEFAULT_WINDOW_SIZE[1],
        min_size=MIN_WINDOW_SIZE,
    )
    api.window = window
    return window


def main() -> None:
    create_app_window()
    webview.start()


if __name__ == "__main__":
    main()
