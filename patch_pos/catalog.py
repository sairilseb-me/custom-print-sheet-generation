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


def _has_stale_schema(conn: sqlite3.Connection) -> bool:
    """True if a 'products' table already exists but predates the
    folder_path-keyed schema (e.g. an old sku-keyed catalog.db, which
    has the exact same column *names* -- only the primary key differs,
    so that's what has to be checked) -- `CREATE TABLE IF NOT EXISTS`
    alone would silently leave it broken forever rather than
    self-healing."""
    rows = conn.execute("PRAGMA table_info(products)").fetchall()
    if not rows:
        return False
    primary_key_columns = {row[1] for row in rows if row[5]}  # row[5] is the `pk` flag
    return primary_key_columns != {"folder_path"}


def open_catalog(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    if _has_stale_schema(conn):
        conn.executescript("DROP TABLE IF EXISTS products; DROP TABLE IF EXISTS scan_meta;")
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
    shape: str | None = None,
    sort: str = "sku",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ProductRecord], int]:
    """Partial (case-insensitive) match on SKU or name, optionally
    restricted to one template shape -- since a product is one shape or
    the other (section 4) and an order is locked to one template
    (section 5), filtering the grid by the order's active shape avoids
    showing products that would just error on add. Returns (page of
    results, total match count) for pagination."""
    sort_column = _SORT_COLUMNS.get(sort, _SORT_COLUMNS["sku"])
    like_pattern = f"%{query}%"
    where = "(sku LIKE ? OR name LIKE ?)"
    params: list = [like_pattern, like_pattern]
    if shape is not None:
        where += " AND shape = ?"
        params.append(shape)

    total_count = conn.execute(
        f"SELECT COUNT(*) FROM products WHERE {where}", params
    ).fetchone()[0]

    rows = conn.execute(
        "SELECT folder_path, sku, sku_number, name, shape, source_psd_path, thumbnail_path "
        f"FROM products WHERE {where} ORDER BY {sort_column} LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()

    return [_row_to_product(row) for row in rows], total_count


def get_product_by_folder(conn: sqlite3.Connection, folder_path: str) -> ProductRecord | None:
    row = conn.execute(
        "SELECT folder_path, sku, sku_number, name, shape, source_psd_path, thumbnail_path "
        "FROM products WHERE folder_path = ?",
        (folder_path,),
    ).fetchone()
    return _row_to_product(row) if row is not None else None


def get_library_info(conn: sqlite3.Connection) -> LibraryInfo:
    row = conn.execute(
        "SELECT total_products, total_size_bytes, last_scan_at FROM scan_meta WHERE id = 1"
    ).fetchone()
    if row is None:
        return LibraryInfo(total_products=0, total_size_bytes=0, last_scan_at=None)
    total_products, total_size_bytes, last_scan_at = row
    return LibraryInfo(total_products, total_size_bytes, last_scan_at)
