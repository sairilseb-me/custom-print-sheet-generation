"""Persistent local catalog index (SQLite) built from a library scan --
exists purely to make search/filter/pagination fast over 799+ products
without rescanning the flash drive on every keystroke (see
PROJECT_INSTRUCTIONS.md section 8, step 3). Lives on the flash drive
itself alongside the library, e.g. '/Volumes/MP-JLS/patch_pos_data/catalog.db',
so it travels with the drive across machines.
"""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .library import ProductRecord, ScanResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    folder_path TEXT PRIMARY KEY,
    sku TEXT NOT NULL,
    sku_number INTEGER NOT NULL,
    name TEXT NOT NULL,
    shape TEXT NOT NULL,
    source_psd_path TEXT NOT NULL,
    thumbnail_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_products_sku ON products (sku);

CREATE TABLE IF NOT EXISTS scan_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_scan_at TEXT NOT NULL,
    total_products INTEGER NOT NULL,
    total_size_bytes INTEGER NOT NULL
);
"""

_SORT_COLUMNS = {"sku": "sku_number", "name": "name COLLATE NOCASE"}


@dataclass(frozen=True)
class LibraryInfo:
    total_products: int
    total_size_bytes: int
    last_scan_at: str | None


def open_catalog(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    return conn


def save_scan(conn: sqlite3.Connection, scan_result: ScanResult) -> None:
    """Replace the catalog's contents with the results of a fresh scan."""
    with conn:
        conn.execute("DELETE FROM products")
        conn.executemany(
            "INSERT INTO products "
            "(folder_path, sku, sku_number, name, shape, source_psd_path, thumbnail_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    str(p.folder_path),
                    p.sku,
                    p.sku_number,
                    p.name,
                    p.shape,
                    str(p.source_psd_path),
                    str(p.thumbnail_path) if p.thumbnail_path else None,
                )
                for p in scan_result.products
            ],
        )
        conn.execute("DELETE FROM scan_meta")
        conn.execute(
            "INSERT INTO scan_meta (id, last_scan_at, total_products, total_size_bytes) "
            "VALUES (1, ?, ?, ?)",
            (
                datetime.now(UTC).isoformat(),
                len(scan_result.products),
                scan_result.total_size_bytes,
            ),
        )


def _row_to_product(row: tuple) -> ProductRecord:
    folder_path, sku, sku_number, name, shape, source_psd_path, thumbnail_path = row
    return ProductRecord(
        sku=sku,
        sku_number=sku_number,
        name=name,
        folder_path=Path(folder_path),
        shape=shape,
        source_psd_path=Path(source_psd_path),
        thumbnail_path=Path(thumbnail_path) if thumbnail_path else None,
    )


def search_products(
    conn: sqlite3.Connection,
    query: str = "",
    sort: str = "sku",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ProductRecord], int]:
    """Partial (case-insensitive) match on SKU or name. Returns
    (page of results, total match count) for pagination."""
    sort_column = _SORT_COLUMNS.get(sort, _SORT_COLUMNS["sku"])
    like_pattern = f"%{query}%"

    total_count = conn.execute(
        "SELECT COUNT(*) FROM products WHERE sku LIKE ? OR name LIKE ?",
        (like_pattern, like_pattern),
    ).fetchone()[0]

    rows = conn.execute(
        "SELECT folder_path, sku, sku_number, name, shape, source_psd_path, thumbnail_path "
        f"FROM products WHERE sku LIKE ? OR name LIKE ? ORDER BY {sort_column} LIMIT ? OFFSET ?",
        (like_pattern, like_pattern, limit, offset),
    ).fetchall()

    return [_row_to_product(row) for row in rows], total_count


def get_library_info(conn: sqlite3.Connection) -> LibraryInfo:
    row = conn.execute(
        "SELECT total_products, total_size_bytes, last_scan_at FROM scan_meta WHERE id = 1"
    ).fetchone()
    if row is None:
        return LibraryInfo(total_products=0, total_size_bytes=0, last_scan_at=None)
    total_products, total_size_bytes, last_scan_at = row
    return LibraryInfo(total_products, total_size_bytes, last_scan_at)
