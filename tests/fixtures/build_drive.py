"""Shared helper: builds a tiny fixture 'flash drive' (library + master
template) from the small fixture PSDs, mirroring the real drive layout
at a testable scale. Used by both the Api integration tests and the E2E
tests -- never the production template/library.
"""

import shutil
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent


def build_fixture_drive(tmp_path: Path) -> Path:
    """tmp_path/drive/MyLibrary/<products>, tmp_path/drive/MP Templates/PATCH/<template>.
    Returns the library root path."""
    drive = tmp_path / "drive"
    library_root = drive / "MyLibrary"

    red_dest = library_root / "MP-P-001 - RED" / "3x2-images" / "1-image-template.psd"
    red_dest.parent.mkdir(parents=True)
    shutil.copy(FIXTURES_DIR / "source_red.psd", red_dest)

    blue_dest = library_root / "MP-P-002 - BLUE" / "3x2-images" / "1-image-template.psd"
    blue_dest.parent.mkdir(parents=True)
    shutil.copy(FIXTURES_DIR / "source_blue.psd", blue_dest)

    circular_dest = (
        library_root / "MP-P-003 - YELLOW CIRCULAR" / "3x2-images" / "1-image-template-circular.psd"
    )
    circular_dest.parent.mkdir(parents=True)
    shutil.copy(FIXTURES_DIR / "source_yellow_circular.psd", circular_dest)

    circular2_dest = (
        library_root / "MP-P-004 - PURPLE CIRCULAR" / "3x2-images" / "1-image-template-circular.psd"
    )
    circular2_dest.parent.mkdir(parents=True)
    shutil.copy(FIXTURES_DIR / "source_purple_circular.psd", circular2_dest)

    template_dest = drive / "MP Templates" / "PATCH" / "A4-PATCH-TEMPLATE-NO MIRROR.psd"
    template_dest.parent.mkdir(parents=True)
    shutil.copy(FIXTURES_DIR / "mini_template.psd", template_dest)

    return library_root
