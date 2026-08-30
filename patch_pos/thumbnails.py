"""Product-grid thumbnails -- use the existing 'Product Photo N.jpg' when
a product has one; otherwise flatten the source PSD into a small, cached
preview. See PROJECT_INSTRUCTIONS.md section 4, "Decision -- thumbnails".
"""

import hashlib
from pathlib import Path

from PIL import Image
from psd_tools import PSDImage

from .library import ProductRecord

PREVIEW_MAX_DIMENSION = 300


def _cache_key(product: ProductRecord) -> str:
    # Hash the folder path rather than using it directly as a filename --
    # avoids illegal-filename-character issues from product names.
    return hashlib.sha1(str(product.folder_path).encode("utf-8")).hexdigest() + ".png"


def _render_preview(source_psd_path: Path) -> Image.Image:
    image = PSDImage.open(source_psd_path).composite()
    image.thumbnail((PREVIEW_MAX_DIMENSION, PREVIEW_MAX_DIMENSION))
    return image.convert("RGB")


def get_thumbnail_bytes(product: ProductRecord, cache_dir: Path) -> bytes:
    """Return JPEG/PNG bytes for the product's thumbnail. Existing
    Product Photo jpgs are returned as-is; a flattened-PSD fallback is
    rendered once and cached under `cache_dir` for subsequent calls."""
    if product.thumbnail_path is not None and product.thumbnail_path.is_file():
        return product.thumbnail_path.read_bytes()

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / _cache_key(product)
    if cache_path.is_file():
        return cache_path.read_bytes()

    preview = _render_preview(product.source_psd_path)
    preview.save(cache_path, format="PNG")
    return cache_path.read_bytes()
