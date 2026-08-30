"""Feature-level tests for thumbnail resolution -- existing jpg vs.
flattened-and-cached PSD fallback. Uses the real fixture PSDs (never the
production library), per PROJECT_INSTRUCTIONS.md section 9.2.
"""

from pathlib import Path

from patch_pos.library import ProductRecord
from patch_pos.thumbnails import get_thumbnail_bytes

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _product(thumbnail_path: Path | None) -> ProductRecord:
    return ProductRecord(
        sku="MP-P-001",
        sku_number=1,
        name="TEST",
        folder_path=FIXTURES_DIR,
        shape="rectangular",
        source_psd_path=FIXTURES_DIR / "source_red.psd",
        thumbnail_path=thumbnail_path,
    )


class TestGetThumbnailBytes:
    def test_returns_existing_jpg_verbatim(self, tmp_path):
        jpg_path = tmp_path / "Product Photo 1.jpg"
        jpg_bytes = b"\xff\xd8\xff\xe0fake jpeg content"
        jpg_path.write_bytes(jpg_bytes)

        result = get_thumbnail_bytes(_product(thumbnail_path=jpg_path), cache_dir=tmp_path / "cache")

        assert result == jpg_bytes

    def test_falls_back_to_flattened_psd_when_no_jpg(self, tmp_path):
        cache_dir = tmp_path / "cache"

        result = get_thumbnail_bytes(_product(thumbnail_path=None), cache_dir=cache_dir)

        assert result[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes
        assert len(list(cache_dir.iterdir())) == 1  # rendered once and cached

    def test_second_call_reuses_cache_without_reflattening(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / "cache"
        product = _product(thumbnail_path=None)

        first = get_thumbnail_bytes(product, cache_dir=cache_dir)

        import patch_pos.thumbnails as thumbnails_module

        def _boom(*_args, **_kwargs):
            raise AssertionError("should not re-render on cache hit")

        monkeypatch.setattr(thumbnails_module, "_render_preview", _boom)

        second = get_thumbnail_bytes(product, cache_dir=cache_dir)

        assert second == first
