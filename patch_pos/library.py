"""Product library scanning -- walks a root directory (the flash drive's
'MNP Patch Master List' or an external path the user selects) for SKU
folders and locates each product's compositing source PSD and thumbnail.

See PROJECT_INSTRUCTIONS.md section 4 for the folder conventions this
was built against (confirmed by inspecting the real library, 799 product
folders).
"""

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

# "MP-P-000 - LOGO" / "MP-P-374-LETRAN KNIGHTS HEAD 1620 CIRCULAR" /
# "MP-P-825 - HELLROADS " (trailing space) all need to match -- dash
# spacing around the SKU number is inconsistent in the real library.
_SKU_FOLDER_PATTERN = re.compile(r"^(MP-P-(\d+))\s*-\s*(.+)$")

_THUMBNAIL_DIR_CANDIDATES = (".", "PATCH-PHOTO-TEMPLATE-assets")


@dataclass(frozen=True)
class ProductRecord:
    sku: str
    sku_number: int
    name: str
    folder_path: Path
    shape: str  # "rectangular" | "circular"
    source_psd_path: Path
    thumbnail_path: Path | None


@dataclass(frozen=True)
class ScanResult:
    products: list[ProductRecord]
    total_size_bytes: int


@dataclass(frozen=True)
class DiskUsage:
    total_bytes: int
    used_bytes: int
    free_bytes: int


def parse_sku_folder_name(folder_name: str) -> tuple[str, int, str] | None:
    """'MP-P-000 - LOGO' -> ('MP-P-000', 0, 'LOGO'). None if the folder
    isn't a product folder at all (doesn't start with MP-P-<number>)."""
    match = _SKU_FOLDER_PATTERN.match(folder_name.strip())
    if match is None:
        return None
    sku, number, name = match.groups()
    return sku, int(number), name.strip()


def find_source_psd(folder: Path) -> tuple[str, Path] | None:
    """Locate a product's compositing-source PSD. Returns (shape, path),
    or None if the folder has neither the rectangular nor the circular
    file -- those folders are skipped from the catalog entirely (see
    PROJECT_INSTRUCTIONS.md section 4, "Decision" on unmatched folders).
    """
    rect_path = folder / "3x2-images" / "1-image-template.psd"
    if rect_path.is_file():
        return "rectangular", rect_path

    # Usually inside 3x2-images/, but some folders put it directly at the
    # SKU folder root instead -- check both.
    for circular_path in (
        folder / "3x2-images" / "1-image-template-circular.psd",
        folder / "1-image-template-circular.psd",
    ):
        if circular_path.is_file():
            return "circular", circular_path

    return None


def find_thumbnail(folder: Path) -> Path | None:
    """Find an existing 'Product Photo N.jpg' to use as the thumbnail --
    loose in the folder, or inside a PATCH-PHOTO-TEMPLATE-assets/
    subfolder. Returns None if neither location has one (the caller
    falls back to flattening the source PSD on demand)."""
    for subdir in _THUMBNAIL_DIR_CANDIDATES:
        directory = folder / subdir
        if not directory.is_dir():
            continue
        matches = sorted(directory.glob("Product Photo*.jpg"))
        if matches:
            return matches[0]
    return None


def _dir_size_bytes(root: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            try:
                total += (Path(dirpath) / filename).stat().st_size
            except OSError:
                continue
    return total


def scan_library(root: Path) -> ScanResult:
    root = Path(root)
    products: list[ProductRecord] = []

    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        parsed = parse_sku_folder_name(entry.name)
        if parsed is None:
            continue
        sku, sku_number, name = parsed

        source = find_source_psd(entry)
        if source is None:
            continue
        shape, source_path = source

        products.append(
            ProductRecord(
                sku=sku,
                sku_number=sku_number,
                name=name,
                folder_path=entry,
                shape=shape,
                source_psd_path=source_path,
                thumbnail_path=find_thumbnail(entry),
            )
        )

    return ScanResult(products=products, total_size_bytes=_dir_size_bytes(root))


def get_disk_usage(path: Path) -> DiskUsage:
    usage = shutil.disk_usage(path)
    return DiskUsage(total_bytes=usage.total, used_bytes=usage.used, free_bytes=usage.free)
