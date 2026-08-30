"""Feature-level tests for the SQLite catalog: saving a scan, then
searching/filtering/paginating against it, per PROJECT_INSTRUCTIONS.md
section 9.2. Uses a throwaway temp-file database per test, never the
real flash-drive catalog.
"""

import sqlite3
import threading
from pathlib import Path

import pytest

from patch_pos.catalog import get_library_info, open_catalog, save_scan, search_products
from patch_pos.library import ProductRecord, ScanResult


def _product(sku: str, sku_number: int, name: str, shape: str = "rectangular") -> ProductRecord:
    folder = Path(f"/fake/{sku}")
    return ProductRecord(
        sku=sku,
        sku_number=sku_number,
        name=name,
        folder_path=folder,
        shape=shape,
        source_psd_path=folder / "3x2-images" / "1-image-template.psd",
        thumbnail_path=None,
    )


FIXTURE_PRODUCTS = [
    _product("MP-P-000", 0, "LOGO"),
    _product("MP-P-001", 1, "POGI"),
    _product("MP-P-002", 2, "MAGANDA"),
    _product("MP-P-051", 51, "ARMY", shape="rectangular"),
    _product("MP-P-352", 352, "MAPUA LOGO CIRCULAR", shape="circular"),
]


@pytest.fixture
def catalog(tmp_path):
    conn = open_catalog(tmp_path / "catalog.db")
    save_scan(conn, ScanResult(products=FIXTURE_PRODUCTS, total_size_bytes=123456))
    yield conn
    conn.close()


class TestSearchProducts:
    def test_empty_query_returns_all(self, catalog):
        products, total = search_products(catalog, query="")
        assert total == len(FIXTURE_PRODUCTS)
        assert len(products) == len(FIXTURE_PRODUCTS)

    def test_partial_match_by_name_case_insensitive(self, catalog):
        products, total = search_products(catalog, query="log")
        assert total == 2  # "LOGO" and "MAPUA LOGO CIRCULAR"
        assert {p.sku for p in products} == {"MP-P-000", "MP-P-352"}

    def test_partial_match_by_sku(self, catalog):
        products, total = search_products(catalog, query="MP-P-05")
        assert total == 1
        assert products[0].sku == "MP-P-051"

    def test_filters_by_shape(self, catalog):
        products, total = search_products(catalog, shape="circular")
        assert total == 1
        assert products[0].sku == "MP-P-352"

    def test_shape_and_query_combine(self, catalog):
        products, total = search_products(catalog, query="log", shape="rectangular")
        assert total == 1  # "LOGO" is rectangular; "MAPUA LOGO CIRCULAR" is not
        assert products[0].sku == "MP-P-000"

    def test_zero_matches(self, catalog):
        products, total = search_products(catalog, query="nonexistent product xyz")
        assert total == 0
        assert products == []

    def test_pagination_limit_and_offset(self, catalog):
        first_page, total = search_products(catalog, sort="sku", limit=2, offset=0)
        second_page, _ = search_products(catalog, sort="sku", limit=2, offset=2)

        assert total == 5
        assert [p.sku for p in first_page] == ["MP-P-000", "MP-P-001"]
        assert [p.sku for p in second_page] == ["MP-P-002", "MP-P-051"]

    def test_sort_by_name(self, catalog):
        products, _ = search_products(catalog, sort="name", limit=100)
        names = [p.name for p in products]
        assert names == sorted(names, key=str.lower)

    def test_sort_by_sku_is_numeric_not_lexical(self, catalog):
        # "MP-P-2" must sort before "MP-P-51" numerically, not
        # lexically (which would put "MP-P-051" before "MP-P-2").
        products, _ = search_products(catalog, sort="sku", limit=100)
        numbers = [p.sku_number for p in products]
        assert numbers == sorted(numbers)


class TestLibraryInfo:
    def test_reflects_last_scan(self, catalog):
        info = get_library_info(catalog)
        assert info.total_products == 5
        assert info.total_size_bytes == 123456
        assert info.last_scan_at is not None

    def test_empty_before_any_scan(self, tmp_path):
        conn = open_catalog(tmp_path / "empty.db")
        info = get_library_info(conn)
        assert info.total_products == 0
        assert info.last_scan_at is None


class TestDuplicateSku:
    def test_two_folders_sharing_a_sku_both_survive_a_scan(self, tmp_path):
        # Real-world data has this: "MP-P-000 - LOGO" and
        # "MP-P-000 - NEW LOGO" both use SKU "MP-P-000". folder_path (not
        # sku) is the catalog's real unique key so neither gets silently
        # dropped.
        conn = open_catalog(tmp_path / "catalog.db")
        products = [
            _product("MP-P-000", 0, "LOGO"),
            ProductRecord(
                sku="MP-P-000",
                sku_number=0,
                name="NEW LOGO",
                folder_path=Path("/fake/MP-P-000 - NEW LOGO"),
                shape="rectangular",
                source_psd_path=Path("/fake/MP-P-000 - NEW LOGO/3x2-images/1-image-template.psd"),
                thumbnail_path=None,
            ),
        ]

        save_scan(conn, ScanResult(products=products, total_size_bytes=1))

        results, total = search_products(conn, query="MP-P-000")
        assert total == 2
        assert {p.name for p in results} == {"LOGO", "NEW LOGO"}


class TestCrossThreadUsage:
    def test_connection_usable_from_a_different_thread(self, tmp_path):
        # pywebview dispatches different JS-bridge calls on different
        # worker threads, not necessarily the thread that created the
        # catalog connection during rescan_library() -- reproduces the
        # "SQLite objects created in a thread can only be used in that
        # same thread" crash seen with a real pywebview session.
        conn = open_catalog(tmp_path / "catalog.db")
        save_scan(conn, ScanResult(products=FIXTURE_PRODUCTS, total_size_bytes=1))

        errors = []

        def query_from_other_thread():
            try:
                search_products(conn, query="")
            except sqlite3.ProgrammingError as exc:
                errors.append(exc)

        thread = threading.Thread(target=query_from_other_thread)
        thread.start()
        thread.join()

        assert errors == []


class TestStaleSchemaSelfHeal:
    def test_pre_folder_path_schema_is_replaced_not_left_broken(self, tmp_path):
        # Simulates a catalog.db written before the folder_path-keyed
        # schema existed (sku as primary key) -- open_catalog must
        # replace it rather than leaving it stuck via
        # "CREATE TABLE IF NOT EXISTS".
        db_path = tmp_path / "catalog.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            "CREATE TABLE products (sku TEXT PRIMARY KEY, sku_number INTEGER, name TEXT, "
            "folder_path TEXT, shape TEXT, source_psd_path TEXT, thumbnail_path TEXT);"
        )
        conn.close()

        conn = open_catalog(db_path)

        pk_columns = {row[1] for row in conn.execute("PRAGMA table_info(products)") if row[5]}
        assert pk_columns == {"folder_path"}

        # A duplicate SKU in two different folders (real production data
        # has this -- MP-P-000 is used by two folders) would violate the
        # OLD schema's UNIQUE constraint on sku if the stale table had
        # survived.
        duplicate_sku_product = ProductRecord(
            sku="MP-P-000",
            sku_number=0,
            name="ANOTHER LOGO VARIANT",
            folder_path=Path("/fake/MP-P-000-b"),
            shape="rectangular",
            source_psd_path=Path("/fake/MP-P-000-b/3x2-images/1-image-template.psd"),
            thumbnail_path=None,
        )
        duplicate_sku_products = [*FIXTURE_PRODUCTS, duplicate_sku_product]
        save_scan(conn, ScanResult(products=duplicate_sku_products, total_size_bytes=1))

        products, total = search_products(conn, query="")
        assert total == len(duplicate_sku_products)


class TestRescan:
    def test_rescan_replaces_previous_catalog(self, tmp_path):
        conn = open_catalog(tmp_path / "catalog.db")
        save_scan(conn, ScanResult(products=FIXTURE_PRODUCTS, total_size_bytes=100))

        # Simulate a folder being removed from the library and rescanned.
        remaining = [p for p in FIXTURE_PRODUCTS if p.sku != "MP-P-000"]
        save_scan(conn, ScanResult(products=remaining, total_size_bytes=50))

        products, total = search_products(conn, query="")
        assert total == 4
        assert "MP-P-000" not in {p.sku for p in products}
        assert get_library_info(conn).total_size_bytes == 50
